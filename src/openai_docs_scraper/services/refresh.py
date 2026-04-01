"""Tracked refresh workflow with safe snapshot publication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

from ..db import (
    connect,
    create_run,
    ensure_source,
    init_db,
    publish_snapshot,
    update_run,
)
from .config import get_settings
from .ingestion import ingest_from_cache
from .project import fetch_sitemap, init_project


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_run_id(source_name: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{source_name}-refresh-{stamp}-{uuid4().hex[:8]}"


@dataclass(frozen=True)
class RefreshResult:
    """Summary of a published refresh run."""

    source_name: str
    run_id: str
    snapshot_id: str
    status: str
    trigger: str
    db_path: str
    sitemap_path: str
    pages_total: int
    chunks_total: int
    pages_seen: int
    pages_ingested: int
    pages_unchanged: int
    pages_new: int
    pages_changed: int
    pages_deleted: int
    pages_failed: int
    chunks_written: int
    exports_invalidated: int
    started_at: str
    finished_at: str


class RefreshLockedError(RuntimeError):
    """Raised when a refresh lock is already held by another active process."""


@dataclass(frozen=True)
class RefreshLock:
    """Information about an acquired refresh lock."""

    path: Path
    run_id: str


def _append_jsonl(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _log_event(
    log_path: Path | None,
    *,
    event: str,
    source_name: str,
    run_id: str | None,
    status: str | None = None,
    stage: str | None = None,
    detail: str | None = None,
    stats: dict[str, int] | None = None,
) -> None:
    if log_path is None:
        return
    payload: dict[str, object] = {
        "ts": _utc_now_iso(),
        "event": event,
        "source_name": source_name,
        "run_id": run_id,
    }
    if status is not None:
        payload["status"] = status
    if stage is not None:
        payload["stage"] = stage
    if detail is not None:
        payload["detail"] = detail
    if stats:
        payload["stats"] = stats
    _append_jsonl(log_path, payload)


def _acquire_lock(
    *,
    lock_path: Path,
    run_id: str,
    source_name: str,
    timeout_s: int,
    log_path: Path | None,
) -> RefreshLock:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).timestamp()
    payload = {
        "run_id": run_id,
        "source_name": source_name,
        "pid": os.getpid(),
        "started_at": _utc_now_iso(),
    }
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        stale = False
        existing_detail = None
        try:
            stat = lock_path.stat()
            stale = (now - stat.st_mtime) > timeout_s
            existing_detail = lock_path.read_text(encoding="utf-8")
        except OSError:
            stale = False
        if not stale:
            _log_event(
                log_path,
                event="lock_conflict",
                source_name=source_name,
                run_id=run_id,
                status="skipped",
                stage="locked",
                detail=existing_detail or f"lock held at {lock_path}",
            )
            raise RefreshLockedError(f"refresh lock is active: {lock_path}")
        try:
            lock_path.unlink()
        except OSError as exc:
            raise RefreshLockedError(f"stale refresh lock could not be cleared: {lock_path}") from exc
        _log_event(
            log_path,
            event="lock_recovered",
            source_name=source_name,
            run_id=run_id,
            status="running",
            stage="starting",
            detail=f"recovered stale lock: {lock_path}",
        )
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))
    return RefreshLock(path=lock_path, run_id=run_id)


def _release_lock(lock: RefreshLock | None) -> None:
    if lock is None:
        return
    try:
        lock.path.unlink()
    except FileNotFoundError:
        return


def _update_live_run(
    *,
    db_path: Path,
    run_id: str,
    source_name: str,
    status: str | None = None,
    stage: str | None = None,
    finished_at: str | None = None,
    error_summary: str | None = None,
    stats: dict[str, int] | None = None,
) -> None:
    con = connect(db_path)
    init_db(con)
    update_run(
        con,
        run_id=run_id,
        source_name=source_name,
        status=status,
        stage=stage,
        finished_at=finished_at,
        error_summary=error_summary,
        stats=stats,
    )
    con.close()


def run_refresh(
    *,
    db_path: str | Path | None = None,
    raw_dir: str | Path | None = None,
    sitemap_path: str | Path | None = None,
    source_name: str | None = None,
    sitemap_url: str | None = None,
    fetch_latest_sitemap: bool = True,
    trigger: str = "manual",
    limit: int | None = None,
    mark_missing_deleted: bool = True,
    force: bool = False,
    store_raw_html: bool = False,
    store_raw_body_text: bool = False,
    chunk_max_chars: int | None = None,
    chunk_overlap_chars: int | None = None,
    lock_path: str | Path | None = None,
    lock_timeout_s: int | None = None,
    log_path: str | Path | None = None,
) -> RefreshResult:
    """
    Refresh the active source into a staged SQLite snapshot and publish it on success.

    The live database remains the default retrieval snapshot until the staged refresh
    completes successfully. On failure, the previous database stays in place.
    """

    settings = get_settings()
    source_name = source_name or settings.source_name
    sitemap_url = sitemap_url or settings.sitemap_url
    db_path = Path(db_path or settings.db_path).expanduser().resolve()
    raw_dir = Path(raw_dir or settings.raw_dir).expanduser().resolve()
    sitemap_path = Path(sitemap_path or settings.sitemap_path).expanduser().resolve()
    chunk_max_chars = chunk_max_chars or settings.chunk_max_chars
    chunk_overlap_chars = chunk_overlap_chars or settings.chunk_overlap_chars
    lock_timeout_s = lock_timeout_s or settings.refresh_lock_timeout_s
    resolved_lock_path = (
        Path(lock_path).expanduser().resolve()
        if lock_path is not None
        else (settings.refresh_lock_dir.expanduser().resolve() / f"{source_name}.lock")
    )
    resolved_log_path = (
        Path(log_path).expanduser().resolve()
        if log_path is not None
        else settings.refresh_log_path.expanduser().resolve()
    )

    started_at = _utc_now_iso()
    run_id = _new_run_id(source_name)
    snapshot_id = f"{source_name}-snapshot-{run_id}"
    lock: RefreshLock | None = None

    db_path.parent.mkdir(parents=True, exist_ok=True)
    lock = _acquire_lock(
        lock_path=resolved_lock_path,
        run_id=run_id,
        source_name=source_name,
        timeout_s=lock_timeout_s,
        log_path=resolved_log_path,
    )
    _log_event(
        resolved_log_path,
        event="run_started",
        source_name=source_name,
        run_id=run_id,
        status="running",
        stage="starting",
        detail=f"db={db_path}",
    )

    con = connect(db_path)
    init_db(con)
    ensure_source(con, source_name=source_name, adapter_name=source_name, observed_at=started_at)
    create_run(
        con,
        run_id=run_id,
        source_name=source_name,
        trigger=trigger,
        status="running",
        stage="starting",
        started_at=started_at,
    )
    con.close()

    stage_root = db_path.parent / f".refresh-{run_id}"
    stage_root.mkdir(parents=True, exist_ok=True)
    stage_db_path = stage_root / db_path.name
    stage_sitemap_path = stage_root / sitemap_path.name
    stats: dict[str, int] | None = None

    try:
        if not raw_dir.is_dir():
            raise FileNotFoundError(f"raw_dir not found: {raw_dir}")
        if db_path.is_file():
            shutil.copy2(db_path, stage_db_path)
        else:
            init_project(stage_db_path)

        _update_live_run(db_path=db_path, run_id=run_id, source_name=source_name, stage="discovering")
        _log_event(resolved_log_path, event="stage", source_name=source_name, run_id=run_id, status="running", stage="discovering")
        if fetch_latest_sitemap:
            fetch_sitemap(out_path=stage_sitemap_path, url=sitemap_url)
        else:
            if not sitemap_path.is_file():
                raise FileNotFoundError(f"sitemap not found: {sitemap_path}")
            shutil.copy2(sitemap_path, stage_sitemap_path)

        _update_live_run(db_path=db_path, run_id=run_id, source_name=source_name, stage="ingesting")
        _log_event(resolved_log_path, event="stage", source_name=source_name, run_id=run_id, status="running", stage="ingesting")
        ingest_result = ingest_from_cache(
            db_path=stage_db_path,
            raw_dir=raw_dir,
            run_id=run_id,
            limit=limit,
            mark_missing_deleted=mark_missing_deleted,
            force=force,
            store_raw_html=store_raw_html,
            store_raw_body_text=store_raw_body_text,
            chunk_max_chars=chunk_max_chars,
            chunk_overlap_chars=chunk_overlap_chars,
        )
        stats = {
            "pages_seen": ingest_result.pages_seen,
            "pages_ingested": ingest_result.pages_ingested,
            "pages_unchanged": ingest_result.pages_unchanged,
            "pages_new": ingest_result.pages_new,
            "pages_changed": ingest_result.pages_changed,
            "pages_deleted": ingest_result.pages_deleted,
            "pages_failed": ingest_result.pages_failed,
            "chunks_written": ingest_result.chunks_written,
            "summaries_invalidated": ingest_result.summaries_invalidated,
            "page_embeddings_invalidated": ingest_result.page_embeddings_invalidated,
            "chunk_embeddings_invalidated": ingest_result.chunk_embeddings_invalidated,
            "exports_invalidated": ingest_result.exports_invalidated,
        }

        _update_live_run(db_path=db_path, run_id=run_id, source_name=source_name, stage="publishing")
        _log_event(resolved_log_path, event="stage", source_name=source_name, run_id=run_id, status="running", stage="publishing", stats=stats)
        stage_con = connect(stage_db_path)
        init_db(stage_con)
        ensure_source(stage_con, source_name=source_name, adapter_name=source_name, observed_at=started_at)
        pages_total = int(stage_con.execute("SELECT COUNT(*) FROM pages WHERE deleted_at IS NULL").fetchone()[0])
        chunks_total = int(stage_con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
        finished_at = _utc_now_iso()
        update_run(
            stage_con,
            run_id=run_id,
            source_name=source_name,
            status="succeeded",
            stage="published",
            finished_at=finished_at,
            stats=stats,
        )
        publish_snapshot(
            stage_con,
            snapshot_id=snapshot_id,
            source_name=source_name,
            run_id=run_id,
            created_at=started_at,
            published_at=finished_at,
            db_path=str(db_path),
            export_root=str(settings.md_export_root.expanduser().resolve()),
            sitemap_path=str(sitemap_path),
            pages_total=pages_total,
            chunks_total=chunks_total,
        )
        stage_con.close()

        if stage_sitemap_path.is_file():
            sitemap_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stage_sitemap_path, sitemap_path)
        shutil.copy2(stage_db_path, db_path)

        shutil.rmtree(stage_root, ignore_errors=True)
        _log_event(
            resolved_log_path,
            event="run_succeeded",
            source_name=source_name,
            run_id=run_id,
            status="succeeded",
            stage="published",
            stats={**stats, "pages_total": pages_total, "chunks_total": chunks_total},
        )
        return RefreshResult(
            source_name=source_name,
            run_id=run_id,
            snapshot_id=snapshot_id,
            status="succeeded",
            trigger=trigger,
            db_path=str(db_path),
            sitemap_path=str(sitemap_path),
            pages_total=pages_total,
            chunks_total=chunks_total,
            pages_seen=stats["pages_seen"],
            pages_ingested=stats["pages_ingested"],
            pages_unchanged=stats["pages_unchanged"],
            pages_new=stats["pages_new"],
            pages_changed=stats["pages_changed"],
            pages_deleted=stats["pages_deleted"],
            pages_failed=stats["pages_failed"],
            chunks_written=stats["chunks_written"],
            exports_invalidated=stats["exports_invalidated"],
            started_at=started_at,
            finished_at=finished_at,
        )
    except Exception as exc:
        finished_at = _utc_now_iso()
        _update_live_run(
            db_path=db_path,
            run_id=run_id,
            source_name=source_name,
            status="failed",
            stage="failed",
            finished_at=finished_at,
            error_summary=str(exc),
            stats=stats,
        )
        shutil.rmtree(stage_root, ignore_errors=True)
        _log_event(
            resolved_log_path,
            event="run_failed",
            source_name=source_name,
            run_id=run_id,
            status="failed",
            stage="failed",
            detail=str(exc),
            stats=stats,
        )
        raise
    finally:
        _release_lock(lock)
