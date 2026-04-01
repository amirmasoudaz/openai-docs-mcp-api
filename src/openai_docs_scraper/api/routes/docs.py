"""Read exported docs: index, catalog, and files under configured roots."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas import (
    CatalogEntry,
    ChangeEntryResponse,
    DocsCatalogResponse,
    DocsIndexResponse,
    DocsStatsResponse,
    FileReadResponse,
    PageDiffResponse,
    PageHistoryResponse,
    PageRevisionResponse,
    RunChangesResponse,
)
from ...book_export import rel_md_path_from_url
from ...db import connect, init_db
from ...safe_paths import PathOutsideRootError, resolve_under_root
from ...services.config import get_settings
from ...services.history import diff_page_versions, get_page_history, get_run_changes
from ...services.state import collect_artifact_state

router = APIRouter()


def _media_type(suffix: str) -> str:
    s = suffix.lower()
    if s == ".md":
        return "text/markdown; charset=utf-8"
    if s == ".json":
        return "application/json; charset=utf-8"
    return "text/plain; charset=utf-8"


@router.get("/index", response_model=DocsIndexResponse)
async def get_navigation_index():
    """Return the full `index.md` from the Markdown export directory (table of contents / blurbs)."""
    settings = get_settings()
    root = settings.md_export_root.expanduser().resolve()
    idx = root / "index.md"
    if not idx.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"index.md not found under md_export_root: {root}",
        )
    text = idx.read_text(encoding="utf-8")
    return DocsIndexResponse(path=str(idx), content=text, bytes_length=len(text.encode("utf-8")))


@router.get("/catalog", response_model=DocsCatalogResponse)
async def get_catalog():
    """List all pages in the database with URLs, titles, summaries, and expected split-.md paths."""
    settings = get_settings()
    db_path = settings.db_path.expanduser().resolve()
    if not db_path.is_file():
        raise HTTPException(status_code=404, detail=f"database not found: {db_path}")

    con = connect(db_path)
    init_db(con)
    rows = con.execute(
        """
        SELECT url, title, section, summary, source_path,
               (summary IS NOT NULL AND TRIM(summary) != '') AS has_summary,
               (embedding IS NOT NULL) AS has_page_embedding
        FROM pages
        WHERE deleted_at IS NULL
        ORDER BY url;
        """
    ).fetchall()
    con.close()

    entries: list[CatalogEntry] = []
    for r in rows:
        url = str(r["url"])
        entries.append(
            CatalogEntry(
                url=url,
                title=r["title"],
                section=r["section"],
                summary=r["summary"],
                md_relpath=rel_md_path_from_url(url).as_posix(),
                source_path=r["source_path"],
                has_summary=bool(r["has_summary"]),
                has_page_embedding=bool(r["has_page_embedding"]),
            )
        )
    return DocsCatalogResponse(db_path=str(db_path), count=len(entries), entries=entries)


@router.get("/page/history", response_model=PageHistoryResponse)
async def get_page_history_route(url: str):
    """Return revision history for one page URL."""
    settings = get_settings()
    try:
        result = get_page_history(settings.db_path, url=url)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return PageHistoryResponse(
        url=result.url,
        title=result.title,
        section=result.section,
        current_content_version=result.current_content_version,
        page_state=result.page_state,
        changed_at=result.changed_at,
        deleted_at=result.deleted_at,
        revisions=[
            PageRevisionResponse(
                content_version=revision.content_version,
                content_hash=revision.content_hash,
                observed_at=revision.observed_at,
                title=revision.title,
                section=revision.section,
                source_hash=revision.source_hash,
            )
            for revision in result.revisions
        ],
    )


@router.get("/page/diff", response_model=PageDiffResponse)
async def get_page_diff_route(url: str, from_version: int | None = None, to_version: int | None = None):
    """Return a unified diff between two revisions of one page."""
    settings = get_settings()
    try:
        result = diff_page_versions(
            settings.db_path,
            url=url,
            from_version=from_version,
            to_version=to_version,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return PageDiffResponse(
        url=result.url,
        from_version=result.from_version,
        to_version=result.to_version,
        from_observed_at=result.from_observed_at,
        to_observed_at=result.to_observed_at,
        diff=result.diff,
    )


@router.get("/changes", response_model=RunChangesResponse)
async def get_changes(run_id: str | None = None, limit: int = 50):
    """Return new, changed, and deleted pages for a run, or the latest known run."""
    settings = get_settings()
    try:
        report = get_run_changes(settings.db_path, run_id=run_id, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return RunChangesResponse(
        run_id=report.run_id,
        run_status=report.run_status,
        run_stage=report.run_stage,
        started_at=report.started_at,
        finished_at=report.finished_at,
        new_pages=[ChangeEntryResponse(**entry.__dict__) for entry in report.new_pages],
        changed_pages=[ChangeEntryResponse(**entry.__dict__) for entry in report.changed_pages],
        deleted_pages=[ChangeEntryResponse(**entry.__dict__) for entry in report.deleted_pages],
    )


@router.get("/stats", response_model=DocsStatsResponse)
async def get_stats():
    """Counts for pages/chunks and whether the export index exists."""
    settings = get_settings()
    state = collect_artifact_state(settings)
    if not state.db_exists:
        raise HTTPException(status_code=404, detail=f"database not found: {state.db_path}")

    return DocsStatsResponse(
        source_name=state.source_name,
        available_sources=state.available_sources,
        sitemap_url=state.sitemap_url,
        db_path=state.db_path,
        sitemap_path=state.sitemap_path,
        sitemap_exists=state.sitemap_exists,
        pages_total=state.pages_total,
        pages_deleted=state.pages_deleted,
        pages_failed=state.pages_failed,
        pages_with_plain_text=state.pages_with_plain_text,
        pages_with_summary=state.pages_with_summary,
        pages_with_page_embedding=state.pages_with_page_embedding,
        chunks_total=state.chunks_total,
        chunks_with_embedding=state.chunks_with_embedding,
        stale_summaries=state.stale_summaries,
        stale_page_embeddings=state.stale_page_embeddings,
        stale_exports=state.stale_exports,
        newest_last_seen_at=state.newest_last_seen_at,
        oldest_last_seen_at=state.oldest_last_seen_at,
        latest_run_id=state.latest_run_id,
        latest_run_status=state.latest_run_status,
        latest_run_stage=state.latest_run_stage,
        latest_run_started_at=state.latest_run_started_at,
        latest_run_finished_at=state.latest_run_finished_at,
        latest_run_error_summary=state.latest_run_error_summary,
        latest_successful_run_id=state.latest_successful_run_id,
        active_snapshot_id=state.active_snapshot_id,
        active_snapshot_published_at=state.active_snapshot_published_at,
        active_snapshot_pages_total=state.active_snapshot_pages_total,
        active_snapshot_chunks_total=state.active_snapshot_chunks_total,
        md_export_root=state.md_export_root,
        md_export_root_exists=state.md_export_root_exists,
        index_md_exists=state.index_md_exists,
        raw_dir=state.raw_dir,
        raw_dir_exists=state.raw_dir_exists,
        raw_cache_files=state.raw_cache_files,
    )


@router.get("/export/file/{file_path:path}", response_model=FileReadResponse)
async def read_export_file(file_path: str):
    """
    Read a UTF-8 text file under `md_export_root` (e.g. `guides/structured-outputs.md`).
    Relative path only; `..` rejected.
    """
    settings = get_settings()
    root = settings.md_export_root.expanduser().resolve()
    try:
        path = resolve_under_root(root, file_path)
    except PathOutsideRootError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"file not found: {path}")
    text = path.read_text(encoding="utf-8")
    return FileReadResponse(
        path=str(path),
        root="md_export",
        media_type=_media_type(path.suffix),
        content=text,
        bytes_length=len(text.encode("utf-8")),
    )


@router.get("/raw/file/{file_path:path}", response_model=FileReadResponse)
async def read_raw_file(file_path: str):
    """
    Read a UTF-8 text file under `raw_dir` (cached scrape JSON, e.g. hash-named `.json`).
    """
    settings = get_settings()
    root = settings.raw_dir.expanduser().resolve()
    try:
        path = resolve_under_root(root, file_path)
    except PathOutsideRootError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"file not found: {path}")
    text = path.read_text(encoding="utf-8")
    return FileReadResponse(
        path=str(path),
        root="raw_data",
        media_type=_media_type(path.suffix),
        content=text,
        bytes_length=len(text.encode("utf-8")),
    )
