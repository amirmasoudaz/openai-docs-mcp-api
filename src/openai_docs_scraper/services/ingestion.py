"""Ingestion service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..db import connect, init_db
from ..ingest_cached import ingest_cached_pages


@dataclass(frozen=True)
class IngestionResult:
    """Result of an ingestion operation."""

    pages_seen: int
    pages_ingested: int
    pages_unchanged: int
    pages_new: int
    pages_changed: int
    pages_deleted: int
    chunks_written: int
    summaries_invalidated: int
    page_embeddings_invalidated: int
    chunk_embeddings_invalidated: int


def ingest_from_cache(
    db_path: str | Path,
    raw_dir: str | Path,
    *,
    limit: Optional[int] = None,
    mark_missing_deleted: bool = True,
    force: bool = False,
    store_raw_html: bool = False,
    store_raw_body_text: bool = False,
    chunk_max_chars: int = 2500,
    chunk_overlap_chars: int = 200,
) -> IngestionResult:
    """
    Ingest cached pages from raw JSON files into the database.

    Args:
        db_path: Path to the SQLite database.
        raw_dir: Directory containing raw JSON cache files.
        limit: Maximum number of pages to ingest (None for all).
        force: Force re-ingestion even if content unchanged.
        store_raw_html: Store full raw HTML in database.
        store_raw_body_text: Store raw body text in database.
        chunk_max_chars: Maximum characters per chunk.
        chunk_overlap_chars: Overlap between chunks.

    Returns:
        IngestionResult with statistics.
    """
    db_path = Path(db_path)
    raw_dir = Path(raw_dir)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = connect(db_path)
    init_db(con)

    stats = ingest_cached_pages(
        con=con,
        raw_dir=raw_dir,
        max_pages=limit,
        mark_missing_deleted=mark_missing_deleted,
        force=force,
        store_raw_html=store_raw_html,
        store_raw_body_text=store_raw_body_text,
        chunk_max_chars=chunk_max_chars,
        chunk_overlap_chars=chunk_overlap_chars,
    )

    con.close()

    return IngestionResult(
        pages_seen=stats["pages_seen"],
        pages_ingested=stats["pages_ingested"],
        pages_unchanged=stats["pages_unchanged"],
        pages_new=stats["pages_new"],
        pages_changed=stats["pages_changed"],
        pages_deleted=stats["pages_deleted"],
        chunks_written=stats["chunks_written"],
        summaries_invalidated=stats["summaries_invalidated"],
        page_embeddings_invalidated=stats["page_embeddings_invalidated"],
        chunk_embeddings_invalidated=stats["chunk_embeddings_invalidated"],
    )
