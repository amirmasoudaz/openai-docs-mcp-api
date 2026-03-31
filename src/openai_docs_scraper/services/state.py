"""Artifact and snapshot state helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..db import connect, init_db
from ..sources import list_sources
from .config import Settings


@dataclass(frozen=True)
class ArtifactState:
    """Operational metadata about the current local snapshot and artifacts."""

    source_name: str
    available_sources: list[str]
    sitemap_url: str
    db_path: str
    db_exists: bool
    sitemap_path: str
    sitemap_exists: bool
    raw_dir: str
    raw_dir_exists: bool
    raw_cache_files: int
    md_export_root: str
    md_export_root_exists: bool
    index_md_exists: bool
    pages_total: int
    pages_deleted: int
    pages_with_plain_text: int
    pages_with_summary: int
    pages_with_page_embedding: int
    chunks_total: int
    chunks_with_embedding: int
    stale_summaries: int
    stale_page_embeddings: int
    newest_last_seen_at: str | None
    oldest_last_seen_at: str | None
    latest_run_id: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "available_sources": self.available_sources,
            "sitemap_url": self.sitemap_url,
            "db_path": self.db_path,
            "db_exists": self.db_exists,
            "sitemap_path": self.sitemap_path,
            "sitemap_exists": self.sitemap_exists,
            "raw_dir": self.raw_dir,
            "raw_dir_exists": self.raw_dir_exists,
            "raw_cache_files": self.raw_cache_files,
            "md_export_root": self.md_export_root,
            "md_export_root_exists": self.md_export_root_exists,
            "index_md_exists": self.index_md_exists,
            "pages_total": self.pages_total,
            "pages_deleted": self.pages_deleted,
            "pages_with_plain_text": self.pages_with_plain_text,
            "pages_with_summary": self.pages_with_summary,
            "pages_with_page_embedding": self.pages_with_page_embedding,
            "chunks_total": self.chunks_total,
            "chunks_with_embedding": self.chunks_with_embedding,
            "stale_summaries": self.stale_summaries,
            "stale_page_embeddings": self.stale_page_embeddings,
            "newest_last_seen_at": self.newest_last_seen_at,
            "oldest_last_seen_at": self.oldest_last_seen_at,
            "latest_run_id": self.latest_run_id,
        }


def collect_artifact_state(settings: Settings) -> ArtifactState:
    """Collect filesystem and database-backed artifact state."""
    db = settings.db_path.expanduser().resolve()
    sitemap = settings.sitemap_path.expanduser().resolve()
    raw_dir = settings.raw_dir.expanduser().resolve()
    export_root = settings.md_export_root.expanduser().resolve()

    state = ArtifactState(
        source_name=settings.source_name,
        available_sources=list_sources(),
        sitemap_url=settings.sitemap_url,
        db_path=str(db),
        db_exists=db.is_file(),
        sitemap_path=str(sitemap),
        sitemap_exists=sitemap.is_file(),
        raw_dir=str(raw_dir),
        raw_dir_exists=raw_dir.is_dir(),
        raw_cache_files=len(list(raw_dir.glob("*.json"))) if raw_dir.is_dir() else 0,
        md_export_root=str(export_root),
        md_export_root_exists=export_root.is_dir(),
        index_md_exists=(export_root / "index.md").is_file(),
        pages_total=0,
        pages_deleted=0,
        pages_with_plain_text=0,
        pages_with_summary=0,
        pages_with_page_embedding=0,
        chunks_total=0,
        chunks_with_embedding=0,
        stale_summaries=0,
        stale_page_embeddings=0,
        newest_last_seen_at=None,
        oldest_last_seen_at=None,
        latest_run_id=None,
    )
    if not db.is_file():
        return state

    con = connect(db)
    init_db(con)
    pages_total = int(con.execute("SELECT COUNT(*) FROM pages WHERE deleted_at IS NULL").fetchone()[0])
    pages_deleted = int(con.execute("SELECT COUNT(*) FROM pages WHERE deleted_at IS NOT NULL").fetchone()[0])
    pages_with_plain_text = int(
        con.execute(
            "SELECT COUNT(*) FROM pages WHERE deleted_at IS NULL AND plain_text IS NOT NULL AND TRIM(plain_text) != ''"
        ).fetchone()[0]
    )
    pages_with_summary = int(
        con.execute(
            "SELECT COUNT(*) FROM pages WHERE deleted_at IS NULL AND summary IS NOT NULL AND TRIM(summary) != ''"
        ).fetchone()[0]
    )
    pages_with_page_embedding = int(
        con.execute("SELECT COUNT(*) FROM pages WHERE deleted_at IS NULL AND embedding IS NOT NULL").fetchone()[0]
    )
    chunks_total = int(con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
    chunks_with_embedding = int(con.execute("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL").fetchone()[0])
    stale_summaries = int(
        con.execute(
            """
            SELECT COUNT(*)
            FROM pages
            WHERE deleted_at IS NULL
              AND summary_for_hash IS NOT NULL
              AND content_hash IS NOT NULL
              AND summary_for_hash != content_hash
            """
        ).fetchone()[0]
    )
    stale_page_embeddings = int(
        con.execute(
            """
            SELECT COUNT(*)
            FROM pages
            WHERE deleted_at IS NULL
              AND embedding_for_hash IS NOT NULL
              AND summary_for_hash IS NOT NULL
              AND embedding_for_hash != summary_for_hash
            """
        ).fetchone()[0]
    )
    snapshot_row = con.execute(
        """
        SELECT
          MAX(last_seen_at) AS newest_last_seen_at,
          MIN(last_seen_at) AS oldest_last_seen_at,
          MAX(last_seen_run_id) AS latest_run_id
        FROM pages
        WHERE deleted_at IS NULL;
        """
    ).fetchone()
    con.close()

    return ArtifactState(
        source_name=state.source_name,
        available_sources=state.available_sources,
        sitemap_url=state.sitemap_url,
        db_path=state.db_path,
        db_exists=state.db_exists,
        sitemap_path=state.sitemap_path,
        sitemap_exists=state.sitemap_exists,
        raw_dir=state.raw_dir,
        raw_dir_exists=state.raw_dir_exists,
        raw_cache_files=state.raw_cache_files,
        md_export_root=state.md_export_root,
        md_export_root_exists=state.md_export_root_exists,
        index_md_exists=state.index_md_exists,
        pages_total=pages_total,
        pages_deleted=pages_deleted,
        pages_with_plain_text=pages_with_plain_text,
        pages_with_summary=pages_with_summary,
        pages_with_page_embedding=pages_with_page_embedding,
        chunks_total=chunks_total,
        chunks_with_embedding=chunks_with_embedding,
        stale_summaries=stale_summaries,
        stale_page_embeddings=stale_page_embeddings,
        newest_last_seen_at=snapshot_row["newest_last_seen_at"] if snapshot_row else None,
        oldest_last_seen_at=snapshot_row["oldest_last_seen_at"] if snapshot_row else None,
        latest_run_id=snapshot_row["latest_run_id"] if snapshot_row else None,
    )
