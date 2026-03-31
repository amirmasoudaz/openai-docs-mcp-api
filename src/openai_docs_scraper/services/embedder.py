"""Embedding service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from ..db import connect, init_db
from ..embeddings import pack_f32
from ..env import require_openai_api_key
from ..openai_ops import OpenAIModels, embed_texts


@dataclass(frozen=True)
class EmbedResult:
    """Result of an embedding operation."""

    total_candidates: int
    updated: int


def embed_pages(
    db_path: str | Path,
    *,
    model: Optional[str] = None,
    limit: int = 200,
    force: bool = False,
) -> EmbedResult:
    """
    Generate embeddings for page summaries.

    Args:
        db_path: Path to the SQLite database.
        model: OpenAI embedding model to use.
        limit: Maximum number of pages to embed.
        force: Force re-embedding even if already done.

    Returns:
        EmbedResult with statistics.
    """
    require_openai_api_key()

    if model is None:
        model = OpenAIModels().embedding_model

    db_path = Path(db_path)
    con = connect(db_path)
    init_db(con)

    where = "deleted_at IS NULL AND summary IS NOT NULL"
    if not force:
        where += " AND (embedding IS NULL OR embedding_model != ? OR embedding_for_hash IS NULL OR embedding_for_hash != summary_for_hash)"
        rows = con.execute(
            f"""
            SELECT id, url, summary, summary_for_hash
            FROM pages
            WHERE {where}
            LIMIT ?;
            """,
            (model, limit),
        ).fetchall()
    else:
        rows = con.execute(
            f"""
            SELECT id, url, summary, summary_for_hash
            FROM pages
            WHERE {where}
            LIMIT ?;
            """,
            (limit,),
        ).fetchall()

    total_candidates = len(rows)

    if not rows:
        con.close()
        return EmbedResult(total_candidates=0, updated=0)

    texts = [str(r["summary"]) for r in rows]
    vectors = embed_texts(texts=texts, model=model)

    updated = 0
    for r, v in zip(rows, vectors, strict=True):
        con.execute(
            """
            UPDATE pages
            SET embedding = ?, embedding_model = ?, embedding_updated_at = datetime('now'),
                embedding_for_hash = ?
            WHERE id = ?;
            """,
            (pack_f32(v), model, r["summary_for_hash"], r["id"]),
        )
        updated += 1

    con.commit()
    con.close()

    return EmbedResult(total_candidates=total_candidates, updated=updated)


def embed_chunks(
    db_path: str | Path,
    *,
    model: Optional[str] = None,
    limit: int = 500,
    force: bool = False,
) -> EmbedResult:
    """
    Generate embeddings for chunks.

    Args:
        db_path: Path to the SQLite database.
        model: OpenAI embedding model to use.
        limit: Maximum number of chunks to embed.
        force: Force re-embedding even if already done.

    Returns:
        EmbedResult with statistics.
    """
    require_openai_api_key()

    if model is None:
        model = OpenAIModels().embedding_model

    db_path = Path(db_path)
    con = connect(db_path)
    init_db(con)

    where = "p.deleted_at IS NULL AND c.chunk_text IS NOT NULL"
    params: list[object] = []
    if not force:
        where += " AND (embedding IS NULL OR embedding_model != ? OR embedding_for_hash IS NULL OR embedding_for_hash != chunk_hash)"
        params.append(model)

    rows = con.execute(
        f"""
        SELECT c.id, c.chunk_text, c.chunk_hash
        FROM chunks c
        JOIN pages p ON p.id = c.page_id
        WHERE {where}
        LIMIT ?;
        """,
        (*params, limit),
    ).fetchall()

    total_candidates = len(rows)

    if not rows:
        con.close()
        return EmbedResult(total_candidates=0, updated=0)

    texts = [str(r["chunk_text"]) for r in rows]
    vectors = embed_texts(texts=texts, model=model)

    updated = 0
    for r, v in zip(rows, vectors, strict=True):
        con.execute(
            """
            UPDATE chunks
            SET embedding = ?, embedding_model = ?, embedding_updated_at = datetime('now'),
                embedding_for_hash = ?
            WHERE id = ?;
            """,
            (pack_f32(v), model, r["chunk_hash"], r["id"]),
        )
        updated += 1

    con.commit()
    con.close()

    return EmbedResult(total_candidates=total_candidates, updated=updated)
