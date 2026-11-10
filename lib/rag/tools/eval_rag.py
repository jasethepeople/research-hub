"""Retrieval evaluation: nDCG, MRR, recall@k, bootstrap CI, min-ndcg gate, eval lock."""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from pathlib import Path
from typing import Any

from lib.rag.gate import eval_lock
from lib.rag.retrieve import search

BOOTSTRAP_ROUNDS = 200
BOOTSTRAP_SEED = 1701


def _ranked_docs(connection: sqlite3.Connection, question: str, embedder: Any, mode: str, k: int) -> list[str]:
    hits = search(connection, question, mode=mode, limit=k * 4, embedder=embedder)
    ordered: list[str] = []
    for hit in hits:
        md5 = hit["md5"]
        if md5 not in ordered:
            ordered.append(md5)
    return ordered[:k]


def _ndcg(ranked: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    gain = 0.0
    for position, md5 in enumerate(ranked[:k], start=1):
        if md5 in relevant:
            gain += 1.0 / _log2(position + 1)
    ideal = sum(1.0 / _log2(position + 1) for position in range(1, min(len(relevant), k) + 1))
    return gain / ideal if ideal else 0.0


def _log2(value: int) -> float:
    import math

    return math.log2(value)


def _mrr(ranked: list[str], relevant: set[str]) -> float:
    for position, md5 in enumerate(ranked, start=1):
        if md5 in relevant:
            return 1.0 / position
    return 0.0


def _recall(ranked: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    found = sum(1 for md5 in ranked[:k] if md5 in relevant)
    return found / len(relevant)


def evaluate(
    connection: sqlite3.Connection,
    golden: list[dict[str, Any]],
    embedder: Any,
    *,
    mode: str = "hybrid_rerank",
    k: int = 5,
) -> dict[str, Any]:
    ndcg_values: list[float] = []
    mrr_values: list[float] = []
    recall_values: list[float] = []
    misses: list[dict[str, str]] = []
    for item in golden:
        relevant = {str(item["md5"])}
        ranked = _ranked_docs(connection, item["question"], embedder, mode, k)
        ndcg_values.append(_ndcg(ranked, relevant, k))
        mrr_values.append(_mrr(ranked, relevant))
        recall_values.append(_recall(ranked, relevant, k))
        if item["md5"] not in ranked:
            misses.append({"question": item["question"], "md5": item["md5"]})

    def bootstrap(values: list[float]) -> dict[str, float]:
        if not values:
            return {"low": 0.0, "high": 0.0}
        generator = random.Random(BOOTSTRAP_SEED)
        means = []
        for _ in range(BOOTSTRAP_ROUNDS):
            sample = [values[generator.randrange(len(values))] for _ in values]
            means.append(sum(sample) / len(sample))
        means.sort()
        low = means[int(0.025 * len(means))]
        high = means[min(len(means) - 1, int(0.975 * len(means)))]
        return {"low": min(low, high), "high": max(low, high)}

    return {
        "mode": mode,
        "k": k,
        "queries": len(golden),
        "ndcg": sum(ndcg_values) / len(ndcg_values) if ndcg_values else 0.0,
        "mrr": sum(mrr_values) / len(mrr_values) if mrr_values else 0.0,
        "recall": sum(recall_values) / len(recall_values) if recall_values else 0.0,
        "ndcg_ci": bootstrap(ndcg_values),
        "misses": misses,
    }


def load_golden(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload.get("queries", [])
    return payload


def main(argv: list[str] | None = None) -> int:
    from lib.rag.db import open_db

    parser = argparse.ArgumentParser(description="Evaluate retrieval quality against a golden set.")
    parser.add_argument("--golden", required=True, help="path to golden JSON")
    parser.add_argument("--db", help="path to rag.sqlite3 (defaults to HUB_STATE)")
    parser.add_argument("--mode", default="hybrid_rerank")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--min-ndcg", type=float, default=None, help="exit 1 when nDCG@k falls below this")
    args = parser.parse_args(argv)

    from lib.rag.embed import get_embedder

    connection = open_db(args.db) if args.db else open_db()
    try:
        with eval_lock():
            report = evaluate(connection, load_golden(args.golden), get_embedder(), mode=args.mode, k=args.k)
    finally:
        connection.close()
    print(json.dumps(report, indent=2))
    if args.min_ndcg is not None and report["ndcg"] < args.min_ndcg:
        print(f"nDCG@{args.k} {report['ndcg']:.4f} is below the minimum {args.min_ndcg:.4f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())