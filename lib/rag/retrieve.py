"""Retrieval modes over the RAG store: vector, bm25, hybrid (RRF), hybrid_rerank."""

from __future__ import annotations

import sqlite3
import struct
from collections.abc import Callable, Sequence
from typing import Any

from lib.rag.db import EMBED_DIM, EmbedMismatch, assert_model
from lib.rag.rerank import blend_scores, rerank_texts

RRF_K = 60
RERANK_CANDIDATES = 50
VECTOR_MIN_SIM = 0.15

Embedder = Callable[[Sequence[str]], list[list[float]]]


def _fts_query(query: str) -> str:
    tokens = [token.replace('"', '""') for token in query.split() if token]
    return " ".join(f'"{token}"' for token in tokens)


def _serialize(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def search_vector(
    connection: sqlite3.Connection,
    query: str,
    limit: int,
    embedder: Embedder,
    doc_ids: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    assert_model(connection)
    vector = embedder([query])[0]
    if len(vector) != EMBED_DIM:
        raise EmbedMismatch(f"embedder produced {len(vector)} dimensions, expected {EMBED_DIM}")
    probe = _serialize(vector)
    scope, scope_params = _scope_filter(doc_ids)
    candidate_count = max(limit * 4, 20)
    k = candidate_count * 4
    rows = connection.execute(
        f"""
        SELECT vec_chunks.rowid AS chunk_id, chunks.doc_id, chunks.idx, chunks.text,
               chunks.page, chunks.page_end,
               corpus.md5, corpus.title,
               1.0 - vec_distance_cosine(vec_chunks.embedding, ?) AS similarity
        FROM vec_chunks
        JOIN chunks ON chunks.chunk_id = vec_chunks.rowid
        JOIN corpus ON corpus.doc_id = chunks.doc_id
        WHERE vec_chunks.embedding MATCH ? AND vec_chunks.k = ?{scope}
        ORDER BY distance
        LIMIT ?
        """,
        (probe, probe, k, *scope_params, candidate_count),
    ).fetchall()
    return [
        {
            "chunk_id": row["chunk_id"],
            "doc_id": row["doc_id"],
            "md5": row["md5"],
            "title": row["title"],
            "idx": row["idx"],
            "page": row["page"] or 1,
            "page_end": row["page_end"],
            "text": row["text"],
            "score": row["similarity"],
        }
        for row in rows
        if row["similarity"] >= VECTOR_MIN_SIM
    ][:limit]


def _scope_filter(doc_ids: Sequence[str] | None) -> tuple[str, list[str]]:
    """SQL fragment restricting results to the given doc_ids (16-hex) or md5s (32-hex)."""
    if not doc_ids:
        return "", []
    md5s = [value for value in doc_ids if len(value) == 32]
    ids = [value for value in doc_ids if len(value) != 32]
    clauses: list[str] = []
    params: list[str] = []
    if md5s:
        clauses.append("corpus.md5 IN (" + ", ".join("?" * len(md5s)) + ")")
        params.extend(md5s)
    if ids:
        clauses.append("chunks.doc_id IN (" + ", ".join("?" * len(ids)) + ")")
        params.extend(ids)
    if not clauses:
        return " AND 0", []
    return " AND (" + " OR ".join(clauses) + ")", params


def search_bm25(
    connection: sqlite3.Connection,
    query: str,
    limit: int,
    doc_ids: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    match = _fts_query(query)
    if not match:
        return []
    scope, scope_params = _scope_filter(doc_ids)
    rows = connection.execute(
        f"""
        SELECT chunks.chunk_id, chunks.doc_id, chunks.idx, chunks.text, chunks.page, chunks.page_end,
               corpus.md5, corpus.title, bm25(chunks_fts) AS rank
        FROM chunks_fts
        JOIN chunks ON chunks.chunk_id = chunks_fts.rowid
        JOIN corpus ON corpus.doc_id = chunks.doc_id
        WHERE chunks_fts MATCH ?{scope}
        ORDER BY rank
        LIMIT ?
        """,
        (match, *scope_params, limit),
    ).fetchall()
    return [
        {
            "chunk_id": row["chunk_id"],
            "doc_id": row["doc_id"],
            "md5": row["md5"],
            "title": row["title"],
            "idx": row["idx"],
            "page": row["page"] or 1,
            "page_end": row["page_end"],
            "text": row["text"],
            "score": -row["rank"],
        }
        for row in rows
    ]


def _reciprocal_rank_fusion(
    ranked_lists: list[list[dict[str, Any]]], limit: int
) -> list[dict[str, Any]]:
    fused: dict[int, dict[str, Any]] = {}
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for position, hit in enumerate(ranked, start=1):
            chunk_id = hit["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + position)
            fused.setdefault(chunk_id, hit)
    ordered = sorted(fused.values(), key=lambda hit: scores[hit["chunk_id"]], reverse=True)
    for hit in ordered:
        hit["score"] = scores[hit["chunk_id"]]
    return ordered[:limit]


def search(
    connection: sqlite3.Connection,
    query: str,
    mode: str = "hybrid",
    limit: int = 5,
    embedder: Embedder | None = None,
    reranker: Callable[[str, list[str]], list[float]] | None = None,
    doc_ids: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Dispatch on mode; hybrid fuses vector and bm25 with RRF (k=60).

    doc_ids scopes retrieval to those documents (md5 or doc_id accepted); it is
    applied inside the SQL of both channels so limits stay meaningful.
    """
    if embedder is not None and not callable(embedder) and callable(getattr(embedder, "encode", None)):
        embedder = embedder.encode
    query = " ".join(str(query).split())
    if not query:
        return []
    if mode == "vector":
        if embedder is None:
            raise ValueError("vector mode requires an embedder")
        return search_vector(connection, query, limit, embedder, doc_ids)
    if mode == "bm25":
        return search_bm25(connection, query, limit, doc_ids)
    if mode not in {"hybrid", "hybrid_rerank"}:
        raise ValueError(f"unknown retrieval mode: {mode}")
    if embedder is None:
        raise ValueError("hybrid modes require an embedder")
    candidate_limit = RERANK_CANDIDATES if mode == "hybrid_rerank" else limit
    vector_hits = search_vector(connection, query, candidate_limit, embedder, doc_ids)
    bm25_hits = search_bm25(connection, query, candidate_limit, doc_ids)
    fused = _reciprocal_rank_fusion([vector_hits, bm25_hits], candidate_limit)
    if mode == "hybrid":
        return fused
    candidates = fused
    texts = [hit["text"] for hit in candidates]
    rerank_scores = rerank_texts(query, texts, reranker)
    top_score = max((hit["score"] for hit in candidates), default=1.0) or 1.0
    for hit, rerank_score in zip(candidates, rerank_scores, strict=True):
        hit["score"] = blend_scores(rerank_score, hit["score"] / top_score)
        hit["rerank"] = rerank_score
    candidates.sort(key=lambda hit: hit["score"], reverse=True)
    return candidates[:limit]