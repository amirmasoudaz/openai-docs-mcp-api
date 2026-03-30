"""Summarization and embedding routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..deps import resolve_db_path
from ..schemas import SummarizeRequest, SummarizeResponse, EmbedRequest, EmbedResponse
from ...services import summarize_pages, embed_pages, embed_chunks

router = APIRouter()


@router.post("/summarize", response_model=SummarizeResponse)
async def api_summarize(request: SummarizeRequest):
    """Generate summaries for pages."""
    try:
        result = summarize_pages(
            db_path=resolve_db_path(request.db_path),
            model=request.model,
            limit=request.limit,
            force=request.force,
            section=request.section,
        )
        return SummarizeResponse(
            total_candidates=result.total_candidates,
            updated=result.updated,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/embed", response_model=EmbedResponse)
async def api_embed(request: EmbedRequest):
    """Generate embeddings for pages or chunks."""
    try:
        if request.target == "pages":
            result = embed_pages(
                db_path=resolve_db_path(request.db_path),
                model=request.model,
                limit=request.limit,
                force=request.force,
            )
        else:
            result = embed_chunks(
                db_path=resolve_db_path(request.db_path),
                model=request.model,
                limit=request.limit,
                force=request.force,
            )
        return EmbedResponse(
            total_candidates=result.total_candidates,
            updated=result.updated,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
