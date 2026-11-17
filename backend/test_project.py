import sys, unittest, tempfile, threading, json, urllib.request, urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from engine import *


class EngineTests(unittest.TestCase):
    def test_nested_roundtrip_and_soundness(self):
        g = compile_process(
            "user: Receive\nif Valid?\nparallel\nservice: Register\nbranch\nuser: Contract\nendparallel\nelse\nuser: Reject\nendif\nArchive"
        )
        self.assertEqual(parse_xml(xml(g)), g)
        self.assertTrue(analyze(g)["sound"])

    def test_parallel_join_waits_for_every_branch(self):
        g = compile_process("parallel\nA\nbranch\nB\nendparallel\nC")
        a = analyze(g)
        self.assertTrue(a["sound"])
        self.assertGreater(a["states"], 5)

    def test_xor_parallel_mismatch_is_deadlock(self):
        g = compile_process("if Approved?\nA\nelse\nB\nendif")
        g["nodes"][-2]["type"] = "parallelGateway"
        self.assertTrue(validate(g)["valid"])
        self.assertFalse(analyze(g)["sound"])
        self.assertGreater(analyze(g)["deadlocks"], 0)

    def test_operations_preserve_base(self):
        g = compile_process("A\nB\nC")
        before = copy.deepcopy(g)
        v = derive(
            g,
            [
                {"action": "insert", "target": "N2", "name": "Check"},
                {"action": "modify", "target": "N3", "name": "Revised"},
                {"action": "move", "target": "N4", "after": "N2"},
                {"action": "delete", "target": "N3"},
            ],
        )
        self.assertEqual(g, before)
        self.assertTrue(analyze(v)["sound"])
        self.assertNotEqual(g, v)

    def test_conflict_is_not_silently_ignored(self):
        with self.assertRaises(ValueError):
            derive(compile_process("A"), [{"action": "delete", "target": "missing"}])

    def test_invalid_blocks(self):
        for source in [
            "if X\nA",
            "if X\nelse\nB\nendif",
            "parallel\nA\nendparallel",
            "else",
        ]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                compile_process(source)

    def test_cycle_rejected(self):
        g = compile_process("A\nB")
        g["edges"].append({"id": "Loop", "source": "N3", "target": "N2"})
        self.assertFalse(validate(g)["valid"])

    def test_dtd_rejected(self):
        with self.assertRaises(ValueError):
            parse_xml("<!DOCTYPE foo><foo/>")

    def test_unknown_element_rejected(self):
        g = compile_process("A")
        s = xml(g).replace("bpmn:task", "bpmn:subProcess")
        with self.assertRaises(ValueError):
            parse_xml(s)

    def test_conditional_semantics_rejected(self):
        source = xml(compile_process("A")).replace(
            "</bpmn:task>", "<bpmn:standardLoopCharacteristics /></bpmn:task>"
        )
        with self.assertRaises(ValueError):
            parse_xml(source)

    def test_bound_report_is_incomplete(self):
        self.assertFalse(analyze(compile_process("A\nB"), limit=1)["complete"])


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server

        cls.tmp = tempfile.TemporaryDirectory()
        server.DB = Path(cls.tmp.name) / "test.sqlite"
        server.store.migrate(server.DB)
        cls.srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = "http://127.0.0.1:" + str(cls.srv.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def req(self, path, data=None):
        if data and data.get("family"):
            data = dict(data)
            current = self.req("families/" + data["family"])
            data.setdefault("revision", current["revision"])
            if data.get("id"):
                item = next(
                    (
                        v
                        for v in current["variants"] + current.get("trash", [])
                        if v["id"] == data["id"]
                    ),
                    None,
                )
                if item:
                    data.setdefault("version", item["version"])
        req = urllib.request.Request(
            self.url + "/api/" + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            req, timeout=10
        ) as r:
            return json.load(r)

    def test_lifecycle_persistence_conflict_and_restore(self):
        f = self.req(
            "families", {"name": "Custom process", "source": "Receive\nAssess\nFulfil"}
        )
        fid = f["id"]
        f = self.req(
            "variant",
            {
                "family": fid,
                "name": "EU",
                "context": {"region": "EU"},
                "operations": [
                    {"action": "modify", "target": "N3", "name": "Compliance"}
                ],
            },
        )
        self.assertEqual(f["variants"][0]["status"], "current")
        f = self.req(
            "update-variant",
            {
                "family": fid,
                "id": f["variants"][0]["id"],
                "name": "EU revised",
                "context": {"region": "EU"},
                "operations": [
                    {"action": "modify", "target": "N3", "name": "Updated compliance"}
                ],
            },
        )
        self.assertEqual(f["variants"][0]["name"], "EU revised")
        g = derive(f["graph"], [{"action": "delete", "target": "N3"}])
        f = self.req("save", {"family": fid, "revision": 1, "xml": xml(g)})
        self.assertEqual(f["revision"], 2)
        self.assertEqual(f["variants"][0]["status"], "conflict")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.req("save", {"family": fid, "revision": 1, "xml": xml(g)})
        self.assertEqual(cm.exception.code, 409)
        cm.exception.close()
        f = self.req(
            "restore", {"family": fid, "history": f["history"][-1]["id"], "revision": 2}
        )
        self.assertEqual(f["revision"], 3)
        self.assertEqual(f["variants"][0]["status"], "current")
        saved = self.req("families/" + fid)
        self.assertEqual(saved["graph"], f["graph"])
        self.assertEqual(len(saved["history"]), 3)

    def test_invalid_model_never_saved(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.req("families", {"name": "Broken", "source": "if X\nA"})
        self.assertEqual(cm.exception.code, 400)
        cm.exception.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
