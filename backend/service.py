"""Application workflows. All successful writes return after their transaction commits."""

import json
import hashlib
import time
import uuid
import store
from engine import compile_process, parse_xml, derive, xml, analyze, source_traceability
from validation import (
    AppError,
    text,
    object_value,
    positive_int,
    context_value,
    operations_value,
)


def document(data):
    if data.get("xml"):
        source = text(data["xml"], "BPMN document", 2_000_000)
        return parse_xml(source), source
    source = text(data.get("source"), "Process description", 30000)
    graph = compile_process(source)
    return graph, xml(graph, data.get("name", "Process"))


def check_revision(row, data):
    expected = positive_int(data.get("revision"), "Base revision")
    if row["revision"] != expected:
        raise AppError(
            "The base changed. Reload this family before continuing.",
            409,
            "STALE_REVISION",
            {"revision": row["revision"]},
        )


def variant_row(c, data):
    row = c.execute(
        "SELECT * FROM variants WHERE id=? AND family=?",
        (data.get("id"), data["family"]),
    ).fetchone()
    if row is None:
        raise AppError("Variant not found", 404, "NOT_FOUND")
    if row["version"] != positive_int(data.get("version"), "Variant version"):
        raise AppError(
            "This variant changed in another window. Reload before updating it.",
            409,
            "STALE_VARIANT",
        )
    return row


def import_backup(c, payload):
    object_value(payload, "Backup")
    if "format" in payload:
        if (
            payload.get("format") != "process-family-studio"
            or payload.get("version") != 2
        ):
            raise AppError("Unsupported backup format/version")
        source = object_value(payload.get("family"), "Backup family")
    else:
        source = (
            payload  # Version 1 family exports had no envelope or complete snapshots.
        )
    name = text(source.get("name"), "Backup family name")
    graph, bpmn = document({"xml": source.get("xml")})
    variants = source.get("variants", []) + source.get("trash", [])
    if len(variants) > 200:
        raise AppError("Backup exceeds 200 variants")
    prepared = []
    names = set()
    for v in variants:
        object_value(v, "Backup variant")
        vn = text(v.get("name"), "Variant name")
        if not v.get("deleted") and vn.casefold() in names:
            raise AppError("Backup has duplicate active variant names")
        if not v.get("deleted"):
            names.add(vn.casefold())
        prepared.append(
            (
                vn,
                operations_value(v.get("operations", [])),
                context_value(v.get("context", {})),
                bool(v.get("deleted")),
            )
        )
    history = source.get("history", [])
    if not isinstance(history, list) or len(history) > 10000:
        raise AppError("Backup allows at most 10,000 historical revisions")
    snapshots = []
    for h in history:
        if not isinstance(h, dict) or "snapshot" not in h:
            continue
        snap = object_value(h["snapshot"], "Historical snapshot")
        hg, hx = document({"xml": snap.get("xml")})
        historical_generation = snap.get("generation", {})
        if isinstance(historical_generation, str):
            historical_generation = json.loads(historical_generation)
        object_value(historical_generation, "Historical generation provenance")
        snapshots.append(
            {
                "generation": historical_generation,
                "_created": text(
                    h.get("created", "1970-01-01 00:00:00"), "Historical timestamp", 100
                ),
                "name": text(snap.get("name", name), "Historical family name"),
                "graph": hg,
                "xml": hx,
                "source": text(
                    snap.get("source", ""), "Historical description", 30000, empty=True
                ),
            }
        )
    fid = uuid.uuid4().hex
    # Keep historical content, but assign fresh IDs/revisions to avoid cross-workspace collisions.
    for index, snap in enumerate(snapshots, 1):
        c.execute(
            "INSERT INTO history(family,revision,snapshot,created) VALUES(?,?,?,?)",
            (
                fid,
                index,
                json.dumps({k: v for k, v in snap.items() if k != "_created"}),
                snap["_created"],
            ),
        )
    revision = len(snapshots) + 1
    c.execute(
        "INSERT INTO families(id,name,revision,graph,xml,source) VALUES(?,?,?,?,?,?)",
        (
            fid,
            name,
            revision,
            json.dumps(graph),
            bpmn,
            text(source.get("source", ""), "Description", 30000, empty=True),
        ),
    )
    provenance = source.get("generation", {})
    if isinstance(provenance, str):
        provenance = json.loads(provenance)
    object_value(provenance, "Generation provenance")
    c.execute(
        "UPDATE families SET generation=? WHERE id=?", (json.dumps(provenance), fid)
    )
    for vn, ops, context, deleted in prepared:
        c.execute(
            "INSERT INTO variants(id,family,name,operations,context,version,deleted) VALUES(?,?,?,?,?,1,?)",
            (
                uuid.uuid4().hex,
                fid,
                vn,
                json.dumps(ops),
                json.dumps(context),
                int(deleted),
            ),
        )
    store.snapshot(c, fid)
    old_audit = source.get("audit", [])
    if not isinstance(old_audit, list) or len(old_audit) > 10000:
        raise AppError("Backup audit history is too large")
    for item in old_audit:
        object_value(item, "Audit entry")
        action = text(item.get("action"), "Audit action", 200)
        detail = item.get("detail", "{}")
        if not isinstance(detail, str):
            detail = json.dumps(detail)
        text(detail, "Audit detail", 20000, empty=True)
        created = text(
            item.get("created", "1970-01-01 00:00:00"), "Audit timestamp", 100
        )
        c.execute(
            "INSERT INTO audit(family,action,detail,created) VALUES(?,?,?,?)",
            (fid, action, detail, created),
        )
    store.audit(
        c,
        fid,
        "backup.imported",
        {"variants": len(prepared), "historicalSnapshots": len(snapshots)},
    )
    return fid


def dispatch(db, method, path, data=None):
    if path.startswith("/api/ai/") or path == "/api/generate":
        import generation

        if path == "/api/ai/status" and method == "GET":
            return 200, generation.status()
        if method == "POST":
            object_value(data, "Request")
            if path == "/api/ai/config":
                return 200, generation.configure(data)
            if path == "/api/ai/test":
                response = generation.request_model(
                    [
                        {
                            "role": "user",
                            "content": "Return JSON with one key: status equal to ok.",
                        }
                    ]
                )
                return 200, {
                    "connected": True,
                    "message": "Model responded successfully",
                    "configuration": generation.status(),
                }
            if path == "/api/generate":
                return 200, generation.generate(
                    data.get("source"), data.get("name", "Generated process")
                )
        raise AppError("Endpoint not found", 404, "NOT_FOUND")
    if method == "GET":
        with store.transaction(db) as c:
            if path == "/api/health":
                c.execute("SELECT 1")
                return 200, {
                    "status": "ok",
                    "version": "2.0.0",
                    "schema": store.SCHEMA_VERSION,
                    "mode": "local-single-user",
                }
            if path == "/api/families":
                rows = c.execute(
                    "SELECT f.id,f.name,f.revision,(SELECT COUNT(*) FROM variants v WHERE v.family=f.id AND v.deleted=0) AS variantCount FROM families f ORDER BY f.name,f.id"
                )
                return 200, [dict(r) for r in rows]
            if path.startswith("/api/families/") and (
                len(path.split("/")) == 4
                or len(path.split("/")) == 5
                and path.endswith("/backup")
            ):
                fid = path.split("/")[3]
                if path.endswith("/backup"):
                    return 200, store.export_family(c, fid)
                return 200, store.get_family(c, fid)
        raise AppError("Endpoint not found", 404, "NOT_FOUND")
    object_value(data, "Request")
    if path == "/api/compile":
        graph, bpmn = document(data)
        result = {"graph": graph, "xml": bpmn, "analysis": analyze(graph)}
        if data.get("source") and not data.get("xml"):
            source = text(data["source"], "Description", 30000)
            result.update(
                source=source,
                generation={
                    "mode": "structured",
                    "provider": "offline-compiler",
                    "model": "",
                    "traceability": source_traceability(graph, source),
                },
            )
        return 200, result
    if path == "/api/analyze":
        graph = parse_xml(data["xml"]) if "xml" in data else data.get("graph")
        return 200, analyze(graph)
    if path in {"/api/preview-variant", "/api/preview-base"}:
        with store.transaction(db) as c:
            row = store.require_family(c, text(data.get("family"), "Family ID", 100))
            check_revision(row, data)
            if path == "/api/preview-variant":
                graph = derive(
                    json.loads(row["graph"]),
                    operations_value(data.get("operations", [])),
                )
                return 200, {
                    "graph": graph,
                    "xml": xml(graph, "Recipe preview"),
                    "analysis": analyze(graph),
                }
            graph, bpmn = document(data)
            conflicts = []
            for v in c.execute(
                "SELECT name,operations FROM variants WHERE family=? AND deleted=0",
                (data["family"],),
            ):
                try:
                    derive(graph, json.loads(v["operations"]))
                except ValueError as e:
                    conflicts.append({"name": v["name"], "error": str(e)})
            return 200, {"conflicts": conflicts, "analysis": analyze(graph)}
    allowed = {
        "/api/families",
        "/api/import-backup",
        "/api/save",
        "/api/variant",
        "/api/update-variant",
        "/api/delete-variant",
        "/api/restore-variant",
        "/api/restore",
        "/api/release",
    }
    if path not in allowed:
        raise AppError("Endpoint not found", 404, "NOT_FOUND")
    with store.transaction(db, write=True) as c:
        status = 200
        if path == "/api/families":
            name = text(data.get("name"), "Family name")
            graph, bpmn = document(data)
            fid = uuid.uuid4().hex
            c.execute(
                "INSERT INTO families(id,name,revision,graph,xml,source) VALUES(?,?,?,?,?,?)",
                (
                    fid,
                    name,
                    1,
                    json.dumps(graph),
                    bpmn,
                    text(data.get("source", ""), "Description", 30000, empty=True),
                ),
            )
            provenance = {
                "sourceHash": hashlib.sha256(
                    data.get("source", "").encode()
                ).hexdigest()
            }
            if data.get("generation"):
                generation = object_value(data["generation"], "Generation provenance")
                provenance.update(
                    {
                        k: text(generation.get(k, ""), k, 200, empty=True)
                        for k in ("mode", "provider", "model")
                    }
                )
                traceability = generation.get("traceability", [])
                if not isinstance(traceability, list) or len(traceability) > 250:
                    raise AppError("Invalid source traceability")
                provenance["traceability"] = []
                stored_source = data.get("source", "").strip()
                by_id = {n["id"]: n for n in graph["nodes"]}
                for item in traceability:
                    object_value(item, "Traceability record")
                    node_id = text(item.get("id"), "Evidence node ID", 200)
                    quote = text(item.get("quote"), "Source quote", 1000)
                    start, end = item.get("start"), item.get("end")
                    if (
                        not isinstance(start, int)
                        or not isinstance(end, int)
                        or start < 0
                        or end <= start
                        or stored_source[start:end] != quote
                    ):
                        raise AppError(
                            "Source evidence offsets do not match the current description"
                        )
                    if (
                        node_id not in by_id
                        or by_id[node_id]["name"] != item.get("name")
                        or by_id[node_id]["type"] != item.get("type")
                    ):
                        raise AppError(
                            "Source evidence does not match the generated activity"
                        )
                    provenance["traceability"].append(
                        {
                            "id": node_id,
                            "name": item["name"],
                            "type": item["type"],
                            "quote": quote,
                            "start": start,
                            "end": end,
                        }
                    )
                assumptions = data.get("assumptions", [])
                if not isinstance(assumptions, list) or len(assumptions) > 30:
                    raise AppError("Invalid generation assumptions")
                provenance["assumptions"] = [
                    text(a, "Assumption", 1000) for a in assumptions
                ]
            if not provenance.get("mode"):
                provenance["mode"] = (
                    "structured" if data.get("source") else "imported-bpmn"
                )
            c.execute(
                "UPDATE families SET generation=? WHERE id=?",
                (json.dumps(provenance), fid),
            )
            store.audit(
                c, fid, "family.created", {"name": name, "generation": provenance}
            )
            store.snapshot(c, fid)
            status = 201
        elif path == "/api/import-backup":
            fid = import_backup(c, data.get("backup"))
            status = 201
        else:
            fid = text(data.get("family"), "Family ID", 100)
            row = store.require_family(c, fid)
            check_revision(row, data)
            if path == "/api/save":
                name = text(data.get("name", row["name"]), "Family name")
                graph, bpmn = document(data)
                c.execute(
                    "UPDATE families SET graph=?,xml=?,name=?,revision=revision+1 WHERE id=?",
                    (json.dumps(graph), bpmn, name, fid),
                )
                store.snapshot(c, fid)
                store.audit(c, fid, "base.saved", {"revision": row["revision"] + 1})
            elif path in {"/api/variant", "/api/update-variant"}:
                ops = operations_value(data.get("operations", []))
                context = context_value(data.get("context", {}))
                name = text(data.get("name"), "Variant name")
                derive(json.loads(row["graph"]), ops)
                duplicate = c.execute(
                    "SELECT id FROM variants WHERE family=? AND deleted=0 AND lower(name)=lower(?) AND id<>?",
                    (fid, name, data.get("id", "")),
                ).fetchone()
                if duplicate:
                    raise AppError(
                        "An active variant already has this name", 409, "DUPLICATE_NAME"
                    )
                if path == "/api/variant":
                    if (
                        c.execute(
                            "SELECT COUNT(*) FROM variants WHERE family=?", (fid,)
                        ).fetchone()[0]
                        >= 200
                    ):
                        raise AppError("This family has reached its 200-variant limit")
                    vid = uuid.uuid4().hex
                    c.execute(
                        "INSERT INTO variants(id,family,name,operations,context,version,deleted) VALUES(?,?,?,?,?,1,0)",
                        (vid, fid, name, json.dumps(ops), json.dumps(context)),
                    )
                    store.audit(c, fid, "variant.created", {"id": vid, "name": name})
                else:
                    v = variant_row(c, data)
                    if v["deleted"]:
                        raise AppError(
                            "Restore the variant before editing it",
                            409,
                            "VARIANT_DELETED",
                        )
                    c.execute(
                        "UPDATE variants SET name=?,operations=?,context=?,version=version+1 WHERE id=?",
                        (name, json.dumps(ops), json.dumps(context), v["id"]),
                    )
                    store.audit(
                        c,
                        fid,
                        "variant.updated",
                        {"id": v["id"], "name": name, "version": v["version"] + 1},
                    )
            elif path in {"/api/delete-variant", "/api/restore-variant"}:
                v = variant_row(c, data)
                deleted = int(path == "/api/delete-variant")
                if (
                    not deleted
                    and c.execute(
                        "SELECT 1 FROM variants WHERE family=? AND name=? AND deleted=0 AND id<>?",
                        (fid, v["name"], v["id"]),
                    ).fetchone()
                ):
                    raise AppError(
                        "Rename the active variant with this name before restoring",
                        409,
                        "DUPLICATE_NAME",
                    )
                c.execute(
                    "UPDATE variants SET deleted=?,version=version+1 WHERE id=?",
                    (deleted, v["id"]),
                )
                store.audit(
                    c,
                    fid,
                    "variant.deleted" if deleted else "variant.restored",
                    {"id": v["id"], "name": v["name"]},
                )
            elif path == "/api/restore":
                h = c.execute(
                    "SELECT snapshot FROM history WHERE id=? AND family=?",
                    (positive_int(data.get("history"), "Historical revision ID"), fid),
                ).fetchone()
                if not h:
                    raise AppError("Historical revision not found", 404, "NOT_FOUND")
                snap = json.loads(h[0])
                graph = parse_xml(snap["xml"])
                c.execute(
                    "UPDATE families SET graph=?,xml=?,source=?,name=?,revision=revision+1 WHERE id=?",
                    (json.dumps(graph), snap["xml"], snap["source"], snap["name"], fid),
                )
                provenance = snap.get("generation", {})
                if isinstance(provenance, str):
                    provenance = json.loads(provenance)
                c.execute(
                    "UPDATE families SET generation=? WHERE id=?",
                    (json.dumps(provenance), fid),
                )
                store.snapshot(c, fid)
                store.audit(
                    c,
                    fid,
                    "base.restored",
                    {"snapshot": data["history"], "revision": row["revision"] + 1},
                )
            elif path == "/api/release":
                f = store.get_family(c, fid)
                checks = [
                    {
                        "name": "Base process",
                        "id": "base",
                        "analysis": analyze(f["graph"]),
                    }
                ]
                release_deadline = time.monotonic() + 15
                for v in f["variants"]:
                    if time.monotonic() > release_deadline:
                        checks.append(
                            {
                                "name": v["name"],
                                "id": v["id"],
                                "analysis": {
                                    "valid": True,
                                    "sound": False,
                                    "complete": False,
                                    "reason": "Family validation time budget exceeded",
                                },
                            }
                        )
                        continue
                    checks.append(
                        {
                            "name": v["name"],
                            "id": v["id"],
                            "analysis": (
                                analyze(v["graph"])
                                if v["status"] == "current"
                                else {
                                    "valid": False,
                                    "sound": False,
                                    "complete": False,
                                    "errors": [v["error"]],
                                }
                            ),
                        }
                    )
                manifest = {
                    "family": fid,
                    "baseRevision": row["revision"],
                    "baseHash": hashlib.sha256(
                        json.dumps(
                            f["graph"], sort_keys=True, separators=(",", ":")
                        ).encode()
                    ).hexdigest(),
                    "variants": [
                        {
                            "id": v["id"],
                            "name": v["name"],
                            "version": v["version"],
                            "recipeHash": hashlib.sha256(
                                json.dumps(
                                    {
                                        "operations": v["operations"],
                                        "context": v["context"],
                                    },
                                    sort_keys=True,
                                    separators=(",", ":"),
                                ).encode()
                            ).hexdigest(),
                        }
                        for v in f["variants"]
                    ],
                    "analyzer": "acyclic-token-v2",
                    "stateLimit": 10000,
                }
                fingerprint = hashlib.sha256(
                    json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                approved = all(x["analysis"].get("sound") for x in checks)
                result = {
                    "approved": approved,
                    "manifest": manifest,
                    "fingerprint": fingerprint,
                    "revision": row["revision"],
                    "checks": checks,
                    "scope": "Acyclic control-flow subset; data conditions and production execution are not evaluated.",
                }
                if approved:
                    result["backup"] = store.export_family(c, fid)
                    store.audit(
                        c,
                        fid,
                        "family.release.validated",
                        {"revision": row["revision"], "variants": len(f["variants"])},
                    )
                return status, result  # context manager commits before dispatch returns
        result = store.get_family(c, fid)
    return status, result
