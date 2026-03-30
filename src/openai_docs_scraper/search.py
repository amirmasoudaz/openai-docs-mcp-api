from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .embeddings import normalize_rows, normalize_vec, unpack_f32


@dataclass(frozen=True)
class ChunkHit:
    chunk_id: int
    page_id: int
    url: str
    title: str | None
    summary: str | None
    chunk_text: str
    score: float
    source_path: str | None


@dataclass(frozen=True)
class PageHit:
    page_id: int
    url: str
    title: str | None
    summary: str | None
    score: float
    source_path: str | None


def vector_search_chunks(
    *,
    con,
    query_embedding: list[float],
    limit: int = 10,
    fts_query: str | None = None,
    fts_limit: int = 500,
) -> list[ChunkHit]:
    """
    Returns top chunk hits by cosine similarity.

    If `fts_query` is provided, it first selects candidate chunk ids via FTS5
    and then ranks only those candidates by embedding similarity.
    """
    q = normalize_vec(np.asarray(query_embedding, dtype=np.float32))

    if fts_query:
        candidate_rows = con.execute(
            """
            SELECT c.id
            FROM chunks_fts f
            JOIN chunks c ON c.id = f.rowid
            WHERE chunks_fts MATCH ?
            LIMIT ?;
            """,
            (fts_query, fts_limit),
        ).fetchall()
        candidate_ids = [int(r["id"]) for r in candidate_rows]
        if not candidate_ids:
            return []
        placeholders = ",".join(["?"] * len(candidate_ids))
        rows = con.execute(
            f"""
            SELECT
              c.id AS chunk_id,
              c.page_id AS page_id,
              c.chunk_text AS chunk_text,
              c.embedding AS embedding,
              p.url AS url,
              p.title AS title,
              p.summary AS summary,
              p.source_path AS source_path
            FROM chunks c
            JOIN pages p ON p.id = c.page_id
            WHERE c.embedding IS NOT NULL AND c.id IN ({placeholders});
            """,
            candidate_ids,
        ).fetchall()
    else:
        rows = con.execute(
            """
            SELECT
              c.id AS chunk_id,
              c.page_id AS page_id,
              c.chunk_text AS chunk_text,
              c.embedding AS embedding,
              p.url AS url,
              p.title AS title,
              p.summary AS summary,
              p.source_path AS source_path
            FROM chunks c
            JOIN pages p ON p.id = c.page_id
            WHERE c.embedding IS NOT NULL;
            """
        ).fetchall()

    if not rows:
        return []

    embeddings = []
    meta = []
    for r in rows:
        blob = r["embedding"]
        if blob is None:
            continue
        vec = unpack_f32(blob)
        embeddings.append(vec)
        meta.append(r)

    if not embeddings:
        return []

    mat = normalize_rows(np.vstack(embeddings))
    scores = mat @ q
    top_idx = np.argsort(-scores)[:limit]

    hits: list[ChunkHit] = []
    for i in top_idx:
        r = meta[int(i)]
        hits.append(
            ChunkHit(
                chunk_id=int(r["chunk_id"]),
                page_id=int(r["page_id"]),
                url=str(r["url"]),
                title=r["title"],
                summary=r["summary"],
                chunk_text=str(r["chunk_text"] or ""),
                score=float(scores[int(i)]),
                source_path=r["source_path"],
            )
        )
    return hits


def vector_search_pages(
    *,
    con,
    query_embedding: list[float],
    limit: int = 10,
    fts_query: str | None = None,
    fts_limit: int = 500,
) -> list[PageHit]:
    """Top pages by cosine similarity over `pages.embedding` (summary vectors)."""
    q = normalize_vec(np.asarray(query_embedding, dtype=np.float32))

    if fts_query:
        candidate_rows = con.execute(
            """
            SELECT DISTINCT c.page_id
            FROM chunks_fts f
            JOIN chunks c ON c.id = f.rowid
            WHERE chunks_fts MATCH ?
            LIMIT ?;
            """,
            (fts_query, fts_limit),
        ).fetchall()
        page_ids = [int(r["page_id"]) for r in candidate_rows]
        if not page_ids:
            return []
        placeholders = ",".join(["?"] * len(page_ids))
        rows = con.execute(
            f"""
            SELECT
              p.id AS page_id,
              p.url AS url,
              p.title AS title,
              p.summary AS summary,
              p.embedding AS embedding,
              p.source_path AS source_path
            FROM pages p
            WHERE p.embedding IS NOT NULL AND p.id IN ({placeholders});
            """,
            page_ids,
        ).fetchall()
    else:
        rows = con.execute(
            """
            SELECT
              p.id AS page_id,
              p.url AS url,
              p.title AS title,
              p.summary AS summary,
              p.embedding AS embedding,
              p.source_path AS source_path
            FROM pages p
            WHERE p.embedding IS NOT NULL;
            """
        ).fetchall()

    if not rows:
        return []

    embeddings = []
    meta = []
    for r in rows:
        blob = r["embedding"]
        if blob is None:
            continue
        vec = unpack_f32(blob)
        embeddings.append(vec)
        meta.append(r)

    if not embeddings:
        return []

    mat = normalize_rows(np.vstack(embeddings))
    scores = mat @ q
    top_idx = np.argsort(-scores)[:limit]

    hits: list[PageHit] = []
    for i in top_idx:
        r = meta[int(i)]
        hits.append(
            PageHit(
                page_id=int(r["page_id"]),
                url=str(r["url"]),
                title=r["title"],
                summary=r["summary"],
                score=float(scores[int(i)]),
                source_path=r["source_path"],
            )
        )
    return hits

