"""Search service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from ..book_export import rel_md_path_from_url
from ..db import connect, init_db
from ..openai_ops import OpenAIModels, embed_texts
from ..search import vector_search_chunks, vector_search_pages


@dataclass(frozen=True)
class SearchHit:
    """A single search result."""

    url: str
    title: Optional[str]
    summary: Optional[str]
    chunk_text: str
    score: float
    source_path: Optional[str] = None
    md_relpath: str = ""


def _make_hit(
    *,
    url: str,
    title: Optional[str],
    summary: Optional[str],
    chunk_text: str,
    score: float,
    source_path: Optional[str],
) -> SearchHit:
    return SearchHit(
        url=url,
        title=title,
        summary=summary,
        chunk_text=chunk_text,
        score=score,
        source_path=source_path,
        md_relpath=rel_md_path_from_url(url).as_posix(),
    )


def query(
    db_path: str | Path,
    q: str,
    *,
    k: int = 10,
    fts: bool = False,
    no_embed: bool = False,
    group_pages: bool = True,
    embedding_model: Optional[str] = None,
    target: Literal["chunks", "pages"] = "chunks",
) -> list[SearchHit]:
    """
    Execute a search query.

    Args:
        db_path: Path to the SQLite database.
        q: Query string.
        k: Number of results to return.
        fts: Use FTS5 full-text search as pre-filter.
        no_embed: Use FTS-only search without embeddings.
        group_pages: Return best chunk per page only.
        embedding_model: OpenAI model for query embedding.
        target: Search chunk bodies (`chunks`) or page summaries (`pages`); must match what you embedded.

    Returns:
        List of SearchHit results.
    """
    if embedding_model is None:
        embedding_model = OpenAIModels().embedding_model

    db_path = Path(db_path)
    con = connect(db_path)
    init_db(con)

    if target == "pages" and no_embed:
        terms = [t for t in q.strip().split() if t]
        if not terms:
            con.close()
            return []
        where = " AND ".join(["LOWER(summary) LIKE LOWER(?)" for _ in terms])
        params = [f"%{t}%" for t in terms]
        rows = con.execute(
            f"""
            SELECT url, title, summary, summary AS chunk_text, 0.0 AS rank, source_path
            FROM pages
            WHERE summary IS NOT NULL AND {where}
            LIMIT ?;
            """,
            (*params, k),
        ).fetchall()
        con.close()
        return [
            _make_hit(
                url=str(r["url"]),
                title=r["title"],
                summary=r["summary"],
                chunk_text=(r["chunk_text"] or "").strip(),
                score=float(r["rank"]),
                source_path=r["source_path"],
            )
            for r in rows
        ]

    if no_embed:
        # FTS-only search
        if group_pages:
            rows = con.execute(
                """
                WITH base AS (
                  SELECT
                    p.id AS page_id,
                    p.url AS url,
                    p.title AS title,
                    p.summary AS summary,
                    p.source_path AS source_path,
                    c.chunk_text AS chunk_text,
                    bm25(chunks_fts) AS rank
                  FROM chunks_fts
                  JOIN chunks c ON c.id = chunks_fts.rowid
                  JOIN pages p ON p.id = c.page_id
                  WHERE chunks_fts MATCH ?
                ),
                ranked AS (
                  SELECT
                    url, title, summary, source_path, chunk_text, rank,
                    ROW_NUMBER() OVER (PARTITION BY page_id ORDER BY rank) AS rn
                  FROM base
                )
                SELECT url, title, summary, source_path, chunk_text, rank
                FROM ranked
                WHERE rn = 1
                ORDER BY rank
                LIMIT ?;
                """,
                (q, k),
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT
                  p.url AS url,
                  p.title AS title,
                  p.summary AS summary,
                  p.source_path AS source_path,
                  c.chunk_text AS chunk_text,
                  bm25(chunks_fts) AS rank
                FROM chunks_fts
                JOIN chunks c ON c.id = chunks_fts.rowid
                JOIN pages p ON p.id = c.page_id
                WHERE chunks_fts MATCH ?
                ORDER BY rank
                LIMIT ?;
                """,
                (q, k),
            ).fetchall()

        con.close()

        return [
            _make_hit(
                url=str(r["url"]),
                title=r["title"],
                summary=r["summary"],
                chunk_text=(r["chunk_text"] or "").strip(),
                score=float(r["rank"]),
                source_path=r["source_path"],
            )
            for r in rows
        ]

    # Vector search
    vectors = embed_texts(texts=[q], model=embedding_model)
    qvec = vectors[0]

    if target == "pages":
        hits = vector_search_pages(
            con=con,
            query_embedding=qvec,
            limit=k,
            fts_query=q if fts else None,
        )
        result = [
            _make_hit(
                url=h.url,
                title=h.title,
                summary=h.summary,
                chunk_text=(h.summary or "").strip(),
                score=h.score,
                source_path=h.source_path,
            )
            for h in hits
        ]
    else:
        hits = vector_search_chunks(
            con=con,
            query_embedding=qvec,
            limit=k if not group_pages else k * 3,
            fts_query=q if fts else None,
        )

        if group_pages:
            best_by_url: dict[str, SearchHit] = {}
            for h in hits:
                hit = _make_hit(
                    url=h.url,
                    title=h.title,
                    summary=h.summary,
                    chunk_text=h.chunk_text.strip(),
                    score=h.score,
                    source_path=h.source_path,
                )
                prev = best_by_url.get(h.url)
                if prev is None or hit.score > prev.score:
                    best_by_url[h.url] = hit
            result = sorted(best_by_url.values(), key=lambda x: x.score, reverse=True)[:k]
        else:
            result = [
                _make_hit(
                    url=h.url,
                    title=h.title,
                    summary=h.summary,
                    chunk_text=h.chunk_text.strip(),
                    score=h.score,
                    source_path=h.source_path,
                )
                for h in hits[:k]
            ]

    con.close()
    return result
