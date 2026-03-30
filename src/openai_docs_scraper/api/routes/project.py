"""Project management routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..deps import resolve_db_path, resolve_sitemap_path
from ..schemas import (
    InitProjectRequest,
    InitProjectResponse,
    FetchSitemapRequest,
    FetchSitemapResponse,
    ListSitemapRequest,
    ListSitemapResponse,
    SitemapEntry,
)
from ...services import init_project, fetch_sitemap, list_sitemap_urls

router = APIRouter()


@router.post("/init", response_model=InitProjectResponse)
async def api_init_project(request: InitProjectRequest):
    """Initialize the project database."""
    try:
        path = init_project(resolve_db_path(request.db_path))
        return InitProjectResponse(success=True, db_path=str(path))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sitemap/fetch", response_model=FetchSitemapResponse)
async def api_fetch_sitemap(request: FetchSitemapRequest):
    """Fetch and save sitemap XML."""
    try:
        path = fetch_sitemap(out_path=resolve_sitemap_path(request.out_path), url=request.url)
        return FetchSitemapResponse(success=True, path=str(path), url=request.url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sitemap/list", response_model=ListSitemapResponse)
async def api_list_sitemap(request: ListSitemapRequest):
    """List URLs from sitemap."""
    try:
        entries = list_sitemap_urls(resolve_sitemap_path(request.sitemap_path), limit=request.limit)
        return ListSitemapResponse(
            entries=[SitemapEntry(loc=e.loc, lastmod=e.lastmod) for e in entries],
            total=len(entries),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Sitemap file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
