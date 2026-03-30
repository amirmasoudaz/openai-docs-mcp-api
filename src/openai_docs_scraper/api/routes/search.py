"""Search routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..deps import resolve_db_path
from ..schemas import SearchRequest, SearchResponse, SearchHit
from ...openai_ops import OpenAIModels
from ...services import query as search_query
from ...services.config import get_settings

router = APIRouter()


def _hits_to_schema(hits) -> list[SearchHit]:
    settings = get_settings()
    export_root = settings.md_export_root.expanduser().resolve()
    out: list[SearchHit] = []
    for h in hits:
        exp_abs: str | None = None
        exp_ok = False
        if h.md_relpath:
            exp_abs_p = export_root / h.md_relpath
            try:
                exp_abs_p = exp_abs_p.resolve()
                exp_abs = str(exp_abs_p)
                exp_ok = exp_abs_p.is_file()
            except OSError:
                exp_abs = str(export_root / h.md_relpath)
        out.append(
            SearchHit(
                url=h.url,
                title=h.title,
                summary=h.summary,
                chunk_text=h.chunk_text,
                score=h.score,
                source_path=h.source_path,
                md_relpath=h.md_relpath,
                export_abs_path=exp_abs,
                export_file_exists=exp_ok,
            )
        )
    return out


@router.post("/query", response_model=SearchResponse)
async def api_search_post(request: SearchRequest):
    """Execute a search query (POST)."""
    try:
        db_file = resolve_db_path(request.db_path)
        hits = search_query(
            db_path=db_file,
            q=request.q,
            k=request.k,
            fts=request.fts,
            no_embed=request.no_embed,
            group_pages=request.group_pages,
            embedding_model=request.embedding_model,
            target=request.target,
        )
        emb = request.embedding_model or OpenAIModels().embedding_model
        return SearchResponse(
            hits=_hits_to_schema(hits),
            query=request.q,
            count=len(hits),
            db_path=db_file,
            target=request.target,
            embedding_model=emb,
            fts=request.fts,
            no_embed=request.no_embed,
            group_pages=request.group_pages,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/query", response_model=SearchResponse)
async def api_search_get(
    q: str = Query(..., min_length=1, description="Search query"),
    db_path: Optional[str] = Query(default=None, description="Omit to use Settings.db_path"),
    k: int = Query(default=10, ge=1, le=100),
    fts: bool = Query(default=False),
    no_embed: bool = Query(default=False),
    group_pages: bool = Query(default=True),
    embedding_model: Optional[str] = Query(default=None),
    target: str = Query(default="chunks", description="chunks or pages"),
):
    """Execute a search query (GET)."""
    try:
        tgt = target if target in ("chunks", "pages") else "chunks"
        db_file = resolve_db_path(db_path)
        hits = search_query(
            db_path=db_file,
            q=q,
            k=k,
            fts=fts,
            no_embed=no_embed,
            group_pages=group_pages,
            embedding_model=embedding_model,
            target=tgt,
        )
        emb = embedding_model or OpenAIModels().embedding_model
        return SearchResponse(
            hits=_hits_to_schema(hits),
            query=q,
            count=len(hits),
            db_path=db_file,
            target=tgt,
            embedding_model=emb,
            fts=fts,
            no_embed=no_embed,
            group_pages=group_pages,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
