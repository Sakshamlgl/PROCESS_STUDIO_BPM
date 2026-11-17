"""Operational database backup/check tool. Never copies a live SQLite file unsafely."""

import argparse
import sqlite3
from pathlib import Path
from contextlib import closing
from server import DB


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    backup = sub.add_parser(
        "backup", help="Create a consistent SQLite backup, including WAL contents"
    )
    backup.add_argument("output", type=Path)
    sub.add_parser("check", help="Run SQLite integrity check")
    args = parser.parse_args()
    if not DB.exists():
        raise SystemExit("Database does not exist. Start the application first.")
    with closing(sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)) as source:
        if args.command == "check":
            result = source.execute("PRAGMA integrity_check").fetchone()[0]
            print(result)
            if result != "ok":
                raise SystemExit(1)
        else:
            output = args.output.resolve()
            if output == DB.resolve() or output.exists():
                raise SystemExit(
                    "Choose a new output filename; existing files are never overwritten."
                )
            output.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(output)) as destination:
                source.backup(destination)
            print(f"Consistent database backup saved to {output}")


if __name__ == "__main__":
    main()
