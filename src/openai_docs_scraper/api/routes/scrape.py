"""Scraping routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..deps import resolve_db_path, resolve_sitemap_path
from ..schemas import ScrapeRequest, ScrapeResponse

router = APIRouter()


@router.post("/run", response_model=ScrapeResponse)
async def api_run_scrape(request: ScrapeRequest):
    """
    Run a scraping job.

    Note: This is a synchronous operation that may take a long time.
    Consider running with low limits initially.
    """
    from ...services import run_scrape

    try:
        result = run_scrape(
            db_path=resolve_db_path(request.db_path),
            sitemap_path=resolve_sitemap_path(request.sitemap_path),
            limit=request.limit,
            start=request.start,
            headless=request.headless,
            timeout_s=request.timeout_s,
            skip_existing=request.skip_existing,
        )
        return ScrapeResponse(
            total_urls=result.total_urls,
            scraped=result.scraped,
            skipped=result.skipped,
            errors=result.errors,
            error_details=result.error_details,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
