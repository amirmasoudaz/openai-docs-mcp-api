"""Read exported docs: index, catalog, and files under configured roots."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas import (
    CatalogEntry,
    DocsCatalogResponse,
    DocsIndexResponse,
    DocsStatsResponse,
    FileReadResponse,
)
from ...book_export import rel_md_path_from_url
from ...db import connect, init_db
from ...safe_paths import PathOutsideRootError, resolve_under_root
from ...services.config import get_settings

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


@router.get("/stats", response_model=DocsStatsResponse)
async def get_stats():
    """Counts for pages/chunks and whether the export index exists."""
    settings = get_settings()
    db_path = settings.db_path.expanduser().resolve()
    md_root = settings.md_export_root.expanduser().resolve()
    raw_dir = settings.raw_dir.expanduser().resolve()

    if not db_path.is_file():
        raise HTTPException(status_code=404, detail=f"database not found: {db_path}")

    con = connect(db_path)
    init_db(con)
    pages_total = int(con.execute("SELECT COUNT(*) FROM pages").fetchone()[0])
    pages_with_plain_text = int(
        con.execute(
            "SELECT COUNT(*) FROM pages WHERE plain_text IS NOT NULL AND TRIM(plain_text) != ''"
        ).fetchone()[0]
    )
    pages_with_summary = int(
        con.execute(
            "SELECT COUNT(*) FROM pages WHERE summary IS NOT NULL AND TRIM(summary) != ''"
        ).fetchone()[0]
    )
    pages_with_page_embedding = int(
        con.execute("SELECT COUNT(*) FROM pages WHERE embedding IS NOT NULL").fetchone()[0]
    )
    chunks_total = int(con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
    chunks_with_embedding = int(
        con.execute("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL").fetchone()[0]
    )
    con.close()

    return DocsStatsResponse(
        db_path=str(db_path),
        pages_total=pages_total,
        pages_with_plain_text=pages_with_plain_text,
        pages_with_summary=pages_with_summary,
        pages_with_page_embedding=pages_with_page_embedding,
        chunks_total=chunks_total,
        chunks_with_embedding=chunks_with_embedding,
        md_export_root=str(md_root),
        index_md_exists=(md_root / "index.md").is_file(),
        raw_dir=str(raw_dir),
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
