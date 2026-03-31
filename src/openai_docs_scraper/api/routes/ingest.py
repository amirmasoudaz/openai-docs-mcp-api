"""Ingestion routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..deps import resolve_db_path, resolve_raw_dir
from ..schemas import IngestRequest, IngestResponse
from ...services import ingest_from_cache

router = APIRouter()


@router.post("/cached", response_model=IngestResponse)
async def api_ingest_cached(request: IngestRequest):
    """Ingest cached pages from raw JSON files."""
    try:
        result = ingest_from_cache(
            db_path=resolve_db_path(request.db_path),
            raw_dir=resolve_raw_dir(request.raw_dir),
            limit=request.limit,
            mark_missing_deleted=request.mark_missing_deleted,
            force=request.force,
            store_raw_html=request.store_raw_html,
            store_raw_body_text=request.store_raw_body_text,
            chunk_max_chars=request.chunk_max_chars,
            chunk_overlap_chars=request.chunk_overlap_chars,
        )
        return IngestResponse(
            pages_seen=result.pages_seen,
            pages_ingested=result.pages_ingested,
            pages_unchanged=result.pages_unchanged,
            pages_new=result.pages_new,
            pages_changed=result.pages_changed,
            pages_deleted=result.pages_deleted,
            chunks_written=result.chunks_written,
            summaries_invalidated=result.summaries_invalidated,
            page_embeddings_invalidated=result.page_embeddings_invalidated,
            chunk_embeddings_invalidated=result.chunk_embeddings_invalidated,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
