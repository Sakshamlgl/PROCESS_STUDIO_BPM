"""Workflow, recovery, concurrency, generation-contract and BPMN interoperability tests."""

import copy
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import generation
import store
from engine import compile_process, parse_xml, xml, analyze, derive, validate
from service import dispatch
from validation import AppError


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "workspace.sqlite"
        store.migrate(self.db)
        self.family = self.call(
            "families",
            {
                "name": "Case processing",
                "source": "Receive case\nReview case\nClose case",
            },
        )

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, path, data=None):
        return dispatch(
            self.db, "POST" if data is not None else "GET", "/api/" + path, data
        )[1]

    def create_variant(self, name="EU"):
        return self.call(
            "variant",
            {
                "family": self.family["id"],
                "revision": 1,
                "name": name,
                "operations": [
                    {
                        "id": "Review",
                        "action": "insert",
                        "target": "N2",
                        "name": "Check compliance",
                    }
                ],
                "context": {"Country": "DE"},
            },
        )

    def test_response_is_durable_before_return(self):
        with sqlite3.connect(self.db) as c:
            self.assertEqual(
                c.execute(
                    "SELECT name FROM families WHERE id=?", (self.family["id"],)
                ).fetchone()[0],
                "Case processing",
            )
        c.close()

    def test_soft_delete_restore_and_variant_version(self):
        f = self.create_variant()
        v = f["variants"][0]
        f = self.call(
            "delete-variant",
            {"family": f["id"], "revision": 1, "id": v["id"], "version": 1},
        )
        self.assertEqual(len(f["variants"]), 0)
        self.assertEqual(f["trash"][0]["version"], 2)
        with self.assertRaises(AppError) as cm:
            self.call(
                "restore-variant",
                {"family": f["id"], "revision": 1, "id": v["id"], "version": 1},
            )
        self.assertEqual(cm.exception.status, 409)
        f = self.call(
            "restore-variant",
            {"family": f["id"], "revision": 1, "id": v["id"], "version": 2},
        )
        self.assertEqual(f["variants"][0]["version"], 3)
        self.assertEqual(f["trash"], [])

    def test_backup_roundtrip_history_audit_context_and_trash(self):
        f = self.create_variant()
        v = f["variants"][0]
        f = self.call("save", {"family": f["id"], "revision": 1, "xml": f["xml"]})
        f = self.call(
            "delete-variant",
            {"family": f["id"], "revision": 2, "id": v["id"], "version": 1},
        )
        backup = self.call("families/" + f["id"] + "/backup")
        restored = self.call("import-backup", {"backup": backup})
        self.assertNotEqual(restored["id"], f["id"])
        self.assertEqual(restored["graph"], f["graph"])
        self.assertEqual(restored["trash"][0]["context"], {"Country": "DE"})
        self.assertGreaterEqual(len(restored["history"]), len(f["history"]))
        self.assertEqual(len(restored["audit"]), len(f["audit"]) + 1)

    def test_backup_failure_is_atomic(self):
        backup = self.call("families/" + self.family["id"] + "/backup")
        backup["family"]["audit"] = [{"action": "x", "detail": 4, "created": None}]
        with self.assertRaises(AppError):
            self.call("import-backup", {"backup": backup})
        self.assertEqual(len(self.call("families")), 1)

    def test_legacy_backup_still_imports(self):
        restored = self.call("import-backup", {"backup": self.family})
        self.assertEqual(restored["graph"], self.family["graph"])

    def test_preview_never_changes_persisted_data(self):
        before = self.call("families/" + self.family["id"])
        preview = self.call(
            "preview-variant",
            {
                "family": before["id"],
                "revision": 1,
                "operations": [
                    {"action": "modify", "target": "N2", "name": "Different task"}
                ],
            },
        )
        after = self.call("families/" + self.family["id"])
        self.assertEqual(before, after)
        self.assertNotEqual(preview["graph"], before["graph"])

    def test_conflict_preview_and_repair(self):
        f = self.create_variant()
        v = f["variants"][0]
        g = derive(f["graph"], [{"action": "delete", "target": "N2"}])
        impact = self.call(
            "preview-base", {"family": f["id"], "revision": 1, "xml": xml(g)}
        )
        self.assertEqual(len(impact["conflicts"]), 1)
        f = self.call("save", {"family": f["id"], "revision": 1, "xml": xml(g)})
        self.assertEqual(f["variants"][0]["status"], "conflict")
        f = self.call(
            "update-variant",
            {
                "family": f["id"],
                "revision": 2,
                "id": v["id"],
                "version": v["version"],
                "name": "EU",
                "operations": [
                    {
                        "id": "Review",
                        "action": "insert",
                        "target": "N3",
                        "name": "Check compliance",
                    }
                ],
            },
        )
        self.assertEqual(f["variants"][0]["status"], "current")

    def test_stale_variant_update_rejected(self):
        f = self.create_variant()
        v = f["variants"][0]
        payload = {
            "family": f["id"],
            "revision": 1,
            "id": v["id"],
            "version": 1,
            "name": "EU changed",
            "operations": v["operations"],
        }
        self.call("update-variant", payload)
        with self.assertRaises(AppError) as cm:
            self.call("update-variant", payload)
        self.assertEqual(cm.exception.code, "STALE_VARIANT")

    def test_two_concurrent_base_saves_exactly_one_wins(self):
        outcomes = []
        barrier = threading.Barrier(2)

        def writer():
            barrier.wait()
            try:
                self.call(
                    "save",
                    {
                        "family": self.family["id"],
                        "revision": 1,
                        "xml": self.family["xml"],
                    },
                )
                outcomes.append(200)
            except AppError as e:
                outcomes.append(e.status)

        threads = [threading.Thread(target=writer) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(outcomes), [200, 409])

    def test_release_requires_all_variants_to_be_valid(self):
        f = self.create_variant()
        self.assertTrue(
            self.call("release", {"family": f["id"], "revision": 1})["approved"]
        )
        g = derive(f["graph"], [{"action": "delete", "target": "N2"}])
        self.call("save", {"family": f["id"], "revision": 1, "xml": xml(g)})
        report = self.call("release", {"family": f["id"], "revision": 2})
        self.assertFalse(report["approved"])
        self.assertNotIn("backup", report)

    def test_duplicate_name_and_malformed_context(self):
        self.create_variant()
        with self.assertRaises(AppError):
            self.create_variant("EU")
        with self.assertRaises(AppError):
            self.call(
                "variant",
                {
                    "family": self.family["id"],
                    "revision": 1,
                    "name": "Bad",
                    "context": {"Country": []},
                },
            )

    def test_transaction_rolls_back_audit_and_family_on_failure(self):
        with self.assertRaises(AppError):
            self.call(
                "families",
                {"name": "Rollback", "source": "Task", "generation": {"model": None}},
            )
        self.assertEqual(len(self.call("families")), 1)

    def test_bad_backup_version_rejected(self):
        with self.assertRaises(AppError):
            self.call(
                "import-backup",
                {
                    "backup": {
                        "format": "process-family-studio",
                        "version": 500,
                        "family": {},
                    }
                },
            )


class DiagramTests(unittest.TestCase):
    def test_swimlane_roles_and_documentation_roundtrip(self):
        g = compile_process(
            "user[Finance]: Approve budget\nservice[Operations]: Reserve stock"
        )
        g["nodes"][1]["description"] = "Check the approved budget threshold."
        self.assertEqual(parse_xml(xml(g)), g)
        self.assertTrue(analyze(g)["sound"])

    def test_global_ids_cannot_collide_with_generated_metadata(self):
        g = compile_process("A")
        g["nodes"][1]["id"] = "Process_1"
        g["edges"][0]["target"] = "Process_1"
        g["edges"][1]["source"] = "Process_1"
        self.assertEqual(parse_xml(xml(g)), g)

    def test_foreign_namespace_task_rejected(self):
        source = (
            xml(compile_process("A"))
            .replace("bpmn:task", "foreign:task")
            .replace(
                "<bpmn:definitions ",
                '<bpmn:definitions xmlns:foreign="https://invalid.example" ',
            )
        )
        with self.assertRaises(ValueError):
            parse_xml(source)

    def test_operation_ids_survive_reordering(self):
        g = compile_process("A\nB")
        first = {
            "id": "First",
            "action": "insert",
            "target": "N2",
            "name": "First activity",
        }
        second = {
            "id": "Second",
            "action": "insert",
            "target": "N3",
            "name": "Second activity",
        }
        a = derive(g, [first, second])
        b = derive(g, [second, first])
        self.assertEqual({n["id"] for n in a["nodes"]}, {n["id"] for n in b["nodes"]})

    def test_arbitrary_changed_text_is_compiled_not_template_matched(self):
        for prefix in [
            "Warehouse delta",
            "Hospital alpha",
            "Unlisted service 781",
            "Renewable project",
        ]:
            g = compile_process(
                "user: "
                + prefix
                + " review\nif "
                + prefix
                + " approved?\n"
                + prefix
                + " fulfill\nelse\n"
                + prefix
                + " decline\nendif"
            )
            names = [n["name"] for n in g["nodes"]]
            self.assertIn(prefix + " review", names)
            self.assertIn(prefix + " fulfill", names)
            self.assertTrue(analyze(g)["sound"])

    def test_time_limit_is_explicit_and_not_sound(self):
        a = analyze(compile_process("A"), timeout=-1)
        self.assertFalse(a["sound"])
        self.assertFalse(a["complete"])
        self.assertEqual(a["reason"], "Time limit reached")

    def test_counterexample_is_available_for_deadlock(self):
        g = compile_process("if Good?\nA\nelse\nB\nendif")
        g["nodes"][-2]["type"] = "parallelGateway"
        a = analyze(g)
        self.assertTrue(a["counterexample"])
        self.assertGreater(a["deadlocks"], 0)

    def test_malformed_graph_returns_validation_diagnostics(self):
        for g in [None, [], {"nodes": [{}], "edges": []}, {"nodes": None, "edges": []}]:
            self.assertFalse(validate(g)["valid"])


class ModelGenerationTests(unittest.TestCase):
    def setUp(self):
        self.graph = compile_process("Receive custom request\nReview custom request")
        for node in self.graph["nodes"]:
            if node["type"] == "task":
                node["evidence"] = "request"
        self.response = json.dumps(dict(self.graph, assumptions=[]))

    def test_current_description_is_forwarded_without_substitution(self):
        calls = []

        def fake(messages, config=None):
            calls.append(copy.deepcopy(messages))
            return self.response

        with patch.object(generation, "request_model", side_effect=fake):
            generation.generate("Warehouse receives a request, then reviews it.")
            generation.generate(
                "Clinic receives a request, then reviews it differently."
            )
        self.assertNotEqual(calls[0][1]["content"], calls[1][1]["content"])
        self.assertIn("Clinic", calls[1][1]["content"])

    def test_invalid_graph_is_repaired_once_using_diagnostics(self):
        invalid = json.dumps({"nodes": [], "edges": [], "assumptions": []})
        with patch.object(
            generation, "request_model", side_effect=[invalid, self.response]
        ) as mock:
            result = generation.generate("Review a request")
        self.assertEqual(result["generation"]["attempts"], 2)
        self.assertEqual(mock.call_count, 2)
        self.assertIn("diagnostics", mock.call_args.args[0][-1]["content"].lower())

    def test_invalid_model_output_never_uses_a_canned_process(self):
        with patch.object(generation, "request_model", return_value="not JSON"):
            with self.assertRaises(AppError) as cm:
                generation.generate("An unrelated request")
        self.assertEqual(cm.exception.code, "GENERATION_INVALID")

    def test_missing_model_is_explicit(self):
        with patch.dict(generation._CONFIG, {"model": ""}):
            with self.assertRaises(AppError) as cm:
                generation.generate("Review request")
        self.assertEqual(cm.exception.code, "MODEL_NOT_CONFIGURED")

    def test_credentials_are_redacted(self):
        with patch.dict(
            generation._CONFIG, {"apiKey": "never-export-this", "model": "test-model"}
        ):
            public = json.dumps(generation.status())
            self.assertNotIn("never-export-this", public)
            self.assertNotIn("apiKey", public)

    def test_remote_plain_http_or_embedded_credentials_rejected(self):
        for url in [
            "http://remote.example/v1",
            "https://user:secret@example.org/v1",
            "file:///etc/passwd",
        ]:
            with self.assertRaises(AppError):
                generation.configure(
                    {"provider": "openai-compatible", "baseUrl": url, "model": "test"}
                )


# Additional transport tests use a local fake provider, never a paid/live model.
class ModelTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        cls.requests = []

        class Provider(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                cls.requests.append(
                    {
                        "path": self.path,
                        "body": body,
                        "authorization": self.headers.get("Authorization"),
                    }
                )
                description = body["messages"][-1]["content"]
                graph = compile_process(
                    "Review "
                    + (
                        "changed request"
                        if "changed" in description
                        else "original request"
                    )
                )
                for node in graph["nodes"]:
                    if node["type"] == "task":
                        node["evidence"] = description
                content = json.dumps(dict(graph, assumptions=[]))
                result = (
                    {"message": {"content": content}}
                    if self.path == "/api/chat"
                    else {"choices": [{"message": {"content": content}}]}
                )
                data = json.dumps(result).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = "http://127.0.0.1:" + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_openai_compatible_transport_uses_current_prompt_and_header(self):
        with patch.dict(
            generation._CONFIG,
            {
                "provider": "openai-compatible",
                "baseUrl": self.url + "/v1",
                "model": "test-only",
                "apiKey": "fixture-key",
            },
        ):
            original = generation.generate("Process the original request")
            changed = generation.generate("Process the changed request")
        self.assertNotEqual(original["graph"], changed["graph"])
        self.assertEqual(self.requests[-1]["path"], "/v1/chat/completions")
        self.assertEqual(self.requests[-1]["authorization"], "Bearer fixture-key")
        self.assertIn(
            "changed request", self.requests[-1]["body"]["messages"][-1]["content"]
        )

    def test_ollama_transport_requests_json_without_streaming(self):
        with patch.dict(
            generation._CONFIG,
            {
                "provider": "ollama",
                "baseUrl": self.url,
                "model": "test-only",
                "apiKey": "",
            },
        ):
            result = generation.generate("Process an original request")
        self.assertTrue(result["analysis"]["sound"])
        self.assertFalse(self.requests[-1]["body"]["stream"])
        self.assertEqual(self.requests[-1]["body"]["format"], "json")


class TraceabilityTests(unittest.TestCase):
    def test_compiler_evidence_survives_preview_and_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "test.sqlite"
            store.migrate(db)
            source = "user: Review request\nservice: Check record"
            compiled = dispatch(db, "POST", "/api/compile", {"source": source})[1]
            self.assertEqual(len(compiled["generation"]["traceability"]), 2)
            for evidence in compiled["generation"]["traceability"]:
                self.assertEqual(
                    source[evidence["start"] : evidence["end"]], evidence["quote"]
                )
            f = dispatch(
                db,
                "POST",
                "/api/families",
                {
                    "name": "Evidence demo",
                    "source": source,
                    "xml": compiled["xml"],
                    "generation": compiled["generation"],
                },
            )[1]
            self.assertEqual(
                f["generation"]["traceability"], compiled["generation"]["traceability"]
            )

    def test_historical_source_provenance_survives_backup_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "evidence.sqlite"
            store.migrate(db)
            source = "user: Review request"
            compiled = dispatch(db, "POST", "/api/compile", {"source": source})[1]
            f = dispatch(
                db,
                "POST",
                "/api/families",
                {
                    "name": "Historical evidence",
                    "source": source,
                    "xml": compiled["xml"],
                    "generation": compiled["generation"],
                },
            )[1]
            backup = dispatch(db, "GET", "/api/families/" + f["id"] + "/backup")[1]
            backup["family"]["history"][0]["created"] = "2020-01-01 00:00:00"
            imported = dispatch(db, "POST", "/api/import-backup", {"backup": backup})[1]
            historical = imported["history"][-1]
            self.assertEqual(historical["created"], "2020-01-01 00:00:00")
            restored = dispatch(
                db,
                "POST",
                "/api/restore",
                {
                    "family": imported["id"],
                    "revision": imported["revision"],
                    "history": historical["id"],
                },
            )[1]
            self.assertEqual(
                restored["generation"]["traceability"], f["generation"]["traceability"]
            )

    def test_fabricated_model_evidence_is_rejected(self):
        g = compile_process("Review request")
        g["nodes"][1]["evidence"] = "Made-up supporting source"
        with patch.object(
            generation,
            "request_model",
            return_value=json.dumps(dict(g, assumptions=[])),
        ):
            with self.assertRaises(AppError) as cm:
                generation.generate("Review a request")
        self.assertEqual(cm.exception.code, "GENERATION_INVALID")

    def test_validation_fingerprint_is_reproducible_and_changes_after_recipe_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "test.sqlite"
            store.migrate(db)
            f = dispatch(
                db, "POST", "/api/families", {"name": "Fingerprint", "source": "A\nB"}
            )[1]
            payload = {"family": f["id"], "revision": 1}
            a = dispatch(db, "POST", "/api/release", payload)[1]
            b = dispatch(db, "POST", "/api/release", payload)[1]
            self.assertEqual(a["fingerprint"], b["fingerprint"])
            dispatch(
                db,
                "POST",
                "/api/variant",
                dict(
                    payload,
                    name="Extra check",
                    operations=[{"action": "insert", "target": "N2", "name": "Verify"}],
                ),
            )
            c = dispatch(db, "POST", "/api/release", payload)[1]
            self.assertNotEqual(a["fingerprint"], c["fingerprint"])


class MigrationTests(unittest.TestCase):
    def test_original_database_is_upgraded_without_losing_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "old.sqlite"
            c = sqlite3.connect(db)
            c.execute(
                "CREATE TABLE families(id TEXT PRIMARY KEY,name TEXT,revision INTEGER,graph TEXT,xml TEXT,source TEXT)"
            )
            g = compile_process("Legacy task")
            c.execute(
                "INSERT INTO families VALUES(?,?,?,?,?,?)",
                ("legacy", "Legacy family", 1, json.dumps(g), xml(g), "Legacy task"),
            )
            c.commit()
            c.close()
            store.migrate(db)
            with store.transaction(db) as current:
                f = store.get_family(current, "legacy")
                self.assertEqual(f["name"], "Legacy family")
                self.assertEqual(f["graph"], g)
                self.assertEqual(f["generation"], {})

    def test_future_schema_is_not_downgraded(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "future.sqlite"
            c = sqlite3.connect(db)
            c.execute("PRAGMA user_version=999")
            c.close()
            with self.assertRaises(AppError) as cm:
                store.migrate(db)
            self.assertEqual(cm.exception.code, "SCHEMA_TOO_NEW")


if __name__ == "__main__":
    unittest.main(verbosity=2)
