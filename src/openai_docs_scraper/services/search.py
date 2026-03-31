"""Search service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from ..book_export import rel_md_path_from_url
from ..db import connect, init_db
from ..openai_ops import OpenAIModels, embed_texts
from ..ranking import RankingCandidate, normalize_query_text, rank_candidates
from ..search import fts_match_query, vector_search_chunks, vector_search_pages


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
    score_details: Optional[dict[str, float]] = None


def _make_hit(
    *,
    url: str,
    title: Optional[str],
    summary: Optional[str],
    chunk_text: str,
    score: float,
    source_path: Optional[str],
    score_details: Optional[dict[str, float]] = None,
) -> SearchHit:
    return SearchHit(
        url=url,
        title=title,
        summary=summary,
        chunk_text=chunk_text,
        score=score,
        source_path=source_path,
        md_relpath=rel_md_path_from_url(url).as_posix(),
        score_details=score_details,
    )


def _search_key(hit: SearchHit, *, group_pages: bool) -> str:
    return hit.url if group_pages else f"{hit.url}::{hit.chunk_text}"


def _merge_for_ranking(
    *,
    query_text: str,
    vector_hits: list[SearchHit],
    lexical_hits: list[SearchHit],
    k: int,
    group_pages: bool,
) -> list[SearchHit]:
    merged: dict[str, RankingCandidate] = {}

    for hit in vector_hits:
        key = _search_key(hit, group_pages=group_pages)
        merged[key] = RankingCandidate(
            url=hit.url,
            title=hit.title,
            summary=hit.summary,
            chunk_text=hit.chunk_text,
            source_path=hit.source_path,
            md_relpath=hit.md_relpath,
            vector_raw=hit.score,
        )

    for hit in lexical_hits:
        key = _search_key(hit, group_pages=group_pages)
        existing = merged.get(key)
        if existing is None:
            merged[key] = RankingCandidate(
                url=hit.url,
                title=hit.title,
                summary=hit.summary,
                chunk_text=hit.chunk_text,
                source_path=hit.source_path,
                md_relpath=hit.md_relpath,
                lexical_raw=hit.score,
            )
            continue
        existing.lexical_raw = hit.score
        if hit.chunk_text:
            existing.chunk_text = hit.chunk_text
        if hit.summary:
            existing.summary = hit.summary

    ranked = rank_candidates(query_text, list(merged.values()), limit=k)
    return [
        _make_hit(
            url=candidate.url,
            title=candidate.title,
            summary=candidate.summary,
            chunk_text=candidate.chunk_text,
            score=candidate.score,
            source_path=candidate.source_path,
            score_details=candidate.score_details,
        )
        for candidate in ranked
    ]


def _fts_chunk_hits(
    con,
    *,
    match_q: str,
    limit: int,
    group_pages: bool,
) -> list[SearchHit]:
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
	              WHERE chunks_fts MATCH ? AND p.deleted_at IS NULL
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
            (match_q, limit),
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
	            WHERE chunks_fts MATCH ? AND p.deleted_at IS NULL
            ORDER BY rank
            LIMIT ?;
            """,
            (match_q, limit),
        ).fetchall()

    return [
        _make_hit(
            url=str(row["url"]),
            title=row["title"],
            summary=row["summary"],
            chunk_text=(row["chunk_text"] or "").strip(),
            score=float(row["rank"]),
            source_path=row["source_path"],
        )
        for row in rows
    ]


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

    normalized_q = normalize_query_text(q)
    db_path = Path(db_path)
    con = connect(db_path)
    init_db(con)
    candidate_limit = max(k * 5, 20)

    if target == "pages" and no_embed:
        terms = [t for t in normalized_q.strip().split() if t]
        if not terms:
            con.close()
            return []
        where = " AND ".join(["LOWER(summary) LIKE LOWER(?)" for _ in terms])
        params = [f"%{t}%" for t in terms]
        rows = con.execute(
            f"""
            SELECT url, title, summary, summary AS chunk_text, 0.0 AS rank, source_path
            FROM pages
            WHERE deleted_at IS NULL AND summary IS NOT NULL AND {where}
            LIMIT ?;
            """,
            (*params, candidate_limit),
        ).fetchall()
        hits = [
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
        ranked = _merge_for_ranking(
            query_text=normalized_q,
            vector_hits=[],
            lexical_hits=hits,
            k=k,
            group_pages=True,
        )
        con.close()
        return ranked

    if no_embed:
        # FTS-only search
        match_q = fts_match_query(normalized_q)
        if not match_q:
            con.close()
            return []
        lexical_hits = _fts_chunk_hits(
            con,
            match_q=match_q,
            limit=candidate_limit,
            group_pages=group_pages,
        )
        ranked = _merge_for_ranking(
            query_text=normalized_q,
            vector_hits=[],
            lexical_hits=lexical_hits,
            k=k,
            group_pages=group_pages,
        )
        con.close()
        return ranked

    # Vector search
    vectors = embed_texts(texts=[normalized_q], model=embedding_model)
    qvec = vectors[0]
    lexical_hits: list[SearchHit] = []
    if fts:
        match_q = fts_match_query(normalized_q)
        if match_q:
            lexical_hits = _fts_chunk_hits(
                con,
                match_q=match_q,
                limit=candidate_limit,
                group_pages=group_pages if target == "chunks" else True,
            )

    if target == "pages":
        hits = vector_search_pages(
            con=con,
            query_embedding=qvec,
            limit=candidate_limit,
            fts_query=None,
        )
        vector_hits = [
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
        result = _merge_for_ranking(
            query_text=normalized_q,
            vector_hits=vector_hits,
            lexical_hits=lexical_hits,
            k=k,
            group_pages=True,
        )
    else:
        hits = vector_search_chunks(
            con=con,
            query_embedding=qvec,
            limit=candidate_limit,
            fts_query=None,
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
            vector_hits = list(best_by_url.values())
        else:
            vector_hits = [
                _make_hit(
                    url=h.url,
                    title=h.title,
                    summary=h.summary,
                    chunk_text=h.chunk_text.strip(),
                    score=h.score,
                    source_path=h.source_path,
                )
                for h in hits
            ]
        result = _merge_for_ranking(
            query_text=normalized_q,
            vector_hits=vector_hits,
            lexical_hits=lexical_hits,
            k=k,
            group_pages=group_pages,
        )

    con.close()
    return result
