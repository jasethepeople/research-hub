"""Golden-set coverage: which questions reference documents missing from the corpus."""

from __future__ import annotations

import argparse
import json
import sqlite3

from lib.rag.tools.eval_rag import load_golden


def coverage(connection: sqlite3.Connection, golden: list[dict]) -> dict:
    stored = {row["md5"] for row in connection.execute("SELECT md5 FROM corpus")}
    missing = [{"question": item["question"], "md5": item["md5"]} for item in golden if item["md5"] not in stored]
    return {
        "queries": len(golden),
        "corpus_docs": len(stored),
        "covered": len(golden) - len(missing),
        "missing": missing,
    }


def main(argv: list[str] | None = None) -> int:
    from lib.rag.db import open_db

    parser = argparse.ArgumentParser(description="Check golden-set coverage against the corpus.")
    parser.add_argument("--golden", required=True)
    parser.add_argument("--db", help="path to rag.sqlite3 (defaults to HUB_STATE)")
    args = parser.parse_args(argv)

    connection = open_db(args.db) if args.db else open_db()
    try:
        report = coverage(connection, load_golden(args.golden))
    finally:
        connection.close()
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())