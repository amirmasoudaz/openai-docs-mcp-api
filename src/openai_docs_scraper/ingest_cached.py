from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .db import insert_page_revision, replace_chunks, upsert_page
from .extract import extract_from_cached_html
from .text import chunk_text_paragraphs, normalize_whitespace, sha256_text


@dataclass(frozen=True)
class CachedPage:
    url: str
    title: str | None
    raw_html: str
    raw_body_text: str | None
    source_hash: str | None
    source_path: Path
    scraped_at: str | None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def iter_cached_pages(raw_dir: str | Path) -> Iterable[CachedPage]:
    raw_dir = Path(raw_dir)
    for path in sorted(raw_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        url = (obj.get("url") or "").strip()
        if not url:
            continue
        title = obj.get("title")
        raw_html = obj.get("raw") or ""
        raw_body_text = obj.get("body")
        source_hash = obj.get("hash")
        scraped_at = None
        try:
            scraped_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            pass
        yield CachedPage(
            url=url,
            title=title,
            raw_html=raw_html,
            raw_body_text=raw_body_text,
            source_hash=source_hash,
            source_path=path,
            scraped_at=scraped_at,
        )


def ingest_cached_pages(
    *,
    con,
    raw_dir: str | Path,
    max_pages: int | None = None,
    mark_missing_deleted: bool = True,
    force: bool = False,
    store_raw_html: bool = False,
    store_raw_body_text: bool = False,
    chunk_max_chars: int = 2500,
    chunk_overlap_chars: int = 200,
) -> dict[str, int]:
    run_id = _utc_now_iso()
    stats = {
        "pages_seen": 0,
        "pages_ingested": 0,
        "pages_unchanged": 0,
        "pages_new": 0,
        "pages_changed": 0,
        "pages_deleted": 0,
        "chunks_written": 0,
        "summaries_invalidated": 0,
        "page_embeddings_invalidated": 0,
        "chunk_embeddings_invalidated": 0,
    }

    for page in iter_cached_pages(raw_dir):
        stats["pages_seen"] += 1
        if max_pages is not None and stats["pages_seen"] > max_pages:
            break

        extracted = extract_from_cached_html(
            url=page.url,
            title=page.title,
            raw_html=page.raw_html,
            raw_body_text=page.raw_body_text,
            make_markdown=False,
            keep_main_html=False,
        )

        content_basis = "\n\n".join(part for part in ((extracted.title or "").strip(), extracted.markdown or extracted.plain_text) if part)
        content_basis = normalize_whitespace(content_basis)
        content_hash = sha256_text(content_basis) if content_basis else None

        # Detect clearly bad cache entries (challenge pages, auth walls, tiny content).
        lowered = (extracted.plain_text or "").lower()
        is_blocked = any(
            m in lowered
            for m in (
                "just a moment",
                "waiting for",
                "cloudflare",
                "enable javascript and cookies",
                "signing in",
            )
        )
        is_too_short = len(extracted.plain_text or "") < 300
        error = None
        if is_blocked or is_too_short:
            error = "blocked_or_too_short"

        existing = con.execute(
            """
            SELECT id, content_hash, content_version, changed_at, summary_for_hash,
                   embedding_for_hash, deleted_at
            FROM pages
            WHERE url = ?;
            """,
            (page.url,),
        ).fetchone()
        if existing and not force and existing["content_hash"] == content_hash:
            con.execute(
                """
                UPDATE pages
                SET title = ?,
                    section = ?,
                    source_path = ?,
                    source_hash = ?,
                    scraped_at = ?,
                    last_seen_at = ?,
                    last_seen_run_id = ?,
                    deleted_at = NULL,
                    deletion_reason = NULL,
                    error = ?
                WHERE id = ?;
                """,
                (
                    extracted.title,
                    extracted.section,
                    str(page.source_path),
                    page.source_hash,
                    page.scraped_at or run_id,
                    run_id,
                    run_id,
                    error,
                    existing["id"],
                ),
            )
            con.commit()
            stats["pages_unchanged"] += 1
            continue

        previous_chunk_stats = {"total": 0, "embedded": 0}
        if existing:
            previous_chunk_stats = con.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) AS embedded
                FROM chunks
                WHERE page_id = ?;
                """,
                (existing["id"],),
            ).fetchone()

        content_changed = bool(existing and existing["content_hash"] != content_hash)
        content_version = 1
        changed_at = run_id
        if existing:
            previous_version = int(existing["content_version"] or 1)
            content_version = previous_version + 1 if content_changed else previous_version
            changed_at = run_id if content_changed else (existing["changed_at"] or run_id)

        if content_changed:
            if existing["summary_for_hash"]:
                stats["summaries_invalidated"] += 1
            if existing["embedding_for_hash"]:
                stats["page_embeddings_invalidated"] += 1
            stats["chunk_embeddings_invalidated"] += int(previous_chunk_stats["embedded"] or 0)

        page_id = upsert_page(
            con,
            url=page.url,
            section=extracted.section,
            title=extracted.title,
            raw_html=extracted.raw_html if store_raw_html else None,
            raw_body_text=extracted.raw_body_text if store_raw_body_text else None,
            main_html=None,
            plain_text=extracted.plain_text,
            content_hash=content_hash,
            scraped_at=page.scraped_at or _utc_now_iso(),
            ingested_at=_utc_now_iso(),
            source_path=str(page.source_path),
            source_hash=page.source_hash,
            http_status=None,
            error=error,
            content_version=content_version,
            changed_at=changed_at,
            last_seen_at=run_id,
            last_seen_run_id=run_id,
            deleted_at=None,
            deletion_reason=None,
        )

        if not existing:
            stats["pages_new"] += 1
            insert_page_revision(
                con,
                page_id=page_id,
                content_version=content_version,
                content_hash=content_hash,
                title=extracted.title,
                observed_at=run_id,
                source_hash=page.source_hash,
            )
        elif content_changed:
            stats["pages_changed"] += 1
            insert_page_revision(
                con,
                page_id=page_id,
                content_version=content_version,
                content_hash=content_hash,
                title=extracted.title,
                observed_at=run_id,
                source_hash=page.source_hash,
            )

        if error:
            stats["pages_ingested"] += 1
            continue

        chunk_source = extracted.plain_text or ""
        chunk_texts = chunk_text_paragraphs(
            chunk_source,
            max_chars=chunk_max_chars,
            overlap_chars=chunk_overlap_chars,
        )
        chunk_rows: list[dict[str, str | int | None]] = []
        for i, txt in enumerate(chunk_texts):
            chash = sha256_text(txt)
            chunk_rows.append(
                {
                    "chunk_index": i,
                    "heading_path": None,
                    "chunk_markdown": None,
                    "chunk_text": txt,
                    "chunk_hash": chash,
                }
            )
        replace_chunks(con, page_id=page_id, chunks=chunk_rows)
        stats["pages_ingested"] += 1
        stats["chunks_written"] += len(chunk_rows)

    if mark_missing_deleted:
        deleted_page_rows = con.execute(
            """
            SELECT id
            FROM pages
            WHERE last_seen_run_id IS NOT NULL
              AND last_seen_run_id != ?
              AND deleted_at IS NULL;
            """,
            (run_id,),
        ).fetchall()
        page_ids = [int(row["id"]) for row in deleted_page_rows]
        if page_ids:
            placeholders = ",".join(["?"] * len(page_ids))
            deleted_chunks = con.execute(
                f"""
                SELECT SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) AS embedded
                FROM chunks
                WHERE page_id IN ({placeholders});
                """,
                page_ids,
            ).fetchone()
            stats["chunk_embeddings_invalidated"] += int((deleted_chunks["embedded"] if deleted_chunks else 0) or 0)
            con.execute(f"DELETE FROM chunks WHERE page_id IN ({placeholders});", page_ids)
            con.execute(
                f"""
                UPDATE pages
                SET deleted_at = ?,
                    deletion_reason = 'missing_from_raw_dir'
                WHERE id IN ({placeholders});
                """,
                (run_id, *page_ids),
            )
            con.commit()
            stats["pages_deleted"] += len(page_ids)

    return stats
