"""SQLite storage and additive migrations. Transactions commit before HTTP success."""

from contextlib import contextmanager, closing
from pathlib import Path
import json
import sqlite3
import uuid
from engine import derive, xml
from validation import AppError

SCHEMA_VERSION = 3


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=10000")
    return c


def migrate(path):
    with closing(connect(path)) as c, c:
        if c.execute("PRAGMA user_version").fetchone()[0] > SCHEMA_VERSION:
            raise AppError(
                "This workspace was created by a newer application version; do not downgrade it",
                409,
                "SCHEMA_TOO_NEW",
            )
        c.execute("PRAGMA journal_mode=WAL")
        c.execute(
            "CREATE TABLE IF NOT EXISTS families(id TEXT PRIMARY KEY, name TEXT NOT NULL, revision INTEGER NOT NULL, graph TEXT NOT NULL, xml TEXT NOT NULL, source TEXT NOT NULL)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS variants(id TEXT PRIMARY KEY, family TEXT NOT NULL, name TEXT NOT NULL, operations TEXT NOT NULL, context TEXT NOT NULL)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, family TEXT, revision INTEGER, snapshot TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        family_cols = {r[1] for r in c.execute("PRAGMA table_info(families)")}
        if "generation" not in family_cols:
            c.execute(
                "ALTER TABLE families ADD COLUMN generation TEXT NOT NULL DEFAULT '{}'"
            )
        cols = {r[1] for r in c.execute("PRAGMA table_info(variants)")}
        for name, declaration in [
            ("version", "INTEGER NOT NULL DEFAULT 1"),
            ("deleted", "INTEGER NOT NULL DEFAULT 0"),
        ]:
            if name not in cols:
                c.execute(f"ALTER TABLE variants ADD COLUMN {name} {declaration}")
        c.execute(
            "CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, family TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_variants_family ON variants(family)")
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_history_family ON history(family, revision)"
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_audit_family ON audit(family, id)")
        c.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    c.close()


@contextmanager
def transaction(path, write=False):
    c = connect(path)
    try:
        c.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield c
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        c.close()


def audit(c, family, action, detail):
    c.execute(
        "INSERT INTO audit(family,action,detail) VALUES(?,?,?)",
        (family, action, json.dumps(detail)),
    )


def snapshot(c, family):
    data = dict(c.execute("SELECT * FROM families WHERE id=?", (family,)).fetchone())
    data["graph"] = json.loads(data["graph"])
    c.execute(
        "INSERT INTO history(family,revision,snapshot) VALUES(?,?,?)",
        (family, data["revision"], json.dumps(data)),
    )


def require_family(c, fid, revision=None):
    row = c.execute("SELECT * FROM families WHERE id=?", (fid,)).fetchone()
    if row is None:
        raise AppError("Family not found", 404, "NOT_FOUND")
    if revision is not None and row["revision"] != revision:
        raise AppError(
            "The base changed in another window. Reload before continuing.",
            409,
            "STALE_REVISION",
            {"revision": row["revision"]},
        )
    return row


def get_family(c, fid):
    f = dict(require_family(c, fid))
    f["graph"] = json.loads(f["graph"])
    f["generation"] = json.loads(f.get("generation") or "{}")
    f["variants"], f["trash"] = [], []
    for row in c.execute(
        "SELECT * FROM variants WHERE family=? ORDER BY name,id", (fid,)
    ):
        v = dict(row)
        v["operations"], v["context"] = json.loads(v["operations"]), json.loads(
            v["context"]
        )
        if v["deleted"]:
            f["trash"].append(v)
            continue
        try:
            v["graph"] = derive(f["graph"], v["operations"])
            v["xml"] = xml(v["graph"], v["name"])
            v["status"] = "current"
        except ValueError as e:
            v["status"], v["error"] = "conflict", str(e)
        f["variants"].append(v)
    f["history"] = [
        dict(r)
        for r in c.execute(
            "SELECT id,revision,created FROM history WHERE family=? ORDER BY id DESC",
            (fid,),
        )
    ]
    f["audit"] = [
        dict(r)
        for r in c.execute(
            "SELECT id,action,detail,created FROM audit WHERE family=? ORDER BY id DESC LIMIT 100",
            (fid,),
        )
    ]
    return f


def export_family(c, fid):
    f = get_family(c, fid)
    f["history"] = [
        dict(r)
        for r in c.execute(
            "SELECT revision,snapshot,created FROM history WHERE family=? ORDER BY id",
            (fid,),
        )
    ]
    for item in f["history"]:
        item["snapshot"] = json.loads(item["snapshot"])
    f["audit"] = [
        dict(r)
        for r in c.execute(
            "SELECT action,detail,created FROM audit WHERE family=? ORDER BY id", (fid,)
        )
    ]
    # Derived diagrams are reproducible; do not duplicate them in backups.
    for v in f["variants"] + f["trash"]:
        for key in ("graph", "xml", "status", "error"):
            v.pop(key, None)
    payload = {"format": "process-family-studio", "version": 2, "family": f}
    if len(json.dumps(payload).encode()) > 9_900_000:
        raise AppError(
            "Family JSON exceeds the 10 MB restore limit. Use manage.py backup for a complete SQLite backup instead.",
            413,
            "BACKUP_TOO_LARGE",
        )
    return payload
