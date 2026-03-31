"""Search routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..deps import resolve_db_path
from ..schemas import AnswerCitation, AnswerFreshness, AnswerRequest, AnswerResponse, SearchRequest, SearchResponse, SearchHit
from ...openai_ops import OpenAIModels
from ...services import answer_question, query as search_query
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
                score_details=h.score_details,
            )
        )
    return out


def _answer_to_schema(result) -> AnswerResponse:
    return AnswerResponse(
        question=result.question,
        answer=result.answer,
        citations=[
            AnswerCitation(
                index=c.index,
                url=c.url,
                title=c.title,
                md_relpath=c.md_relpath,
                export_abs_path=c.export_abs_path,
                export_file_exists=c.export_file_exists,
                source_path=c.source_path,
                snippet=c.snippet,
                score=c.score,
                last_seen_at=c.last_seen_at,
                last_seen_run_id=c.last_seen_run_id,
                content_version=c.content_version,
                stale_summary=c.stale_summary,
                stale_page_embedding=c.stale_page_embedding,
            )
            for c in result.citations
        ],
        warnings=result.warnings,
        freshness=AnswerFreshness(
            oldest_last_seen_at=result.freshness.oldest_last_seen_at,
            newest_last_seen_at=result.freshness.newest_last_seen_at,
            cited_run_ids=result.freshness.cited_run_ids,
            stale_summary_count=result.freshness.stale_summary_count,
            stale_page_embedding_count=result.freshness.stale_page_embedding_count,
            snapshot_age_days=result.freshness.snapshot_age_days,
        ),
        retrieval_target=result.retrieval_target,
        retrieval_k=result.retrieval_k,
        retrieval_fts=result.retrieval_fts,
        retrieval_no_embed=result.retrieval_no_embed,
        synthesis_mode=result.synthesis_mode,
        synthesis_model=result.synthesis_model,
    )


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


@router.post("/answer", response_model=AnswerResponse)
async def api_answer_post(request: AnswerRequest):
    """Answer a question from the local docs snapshot with exact citations."""
    try:
        db_file = resolve_db_path(request.db_path)
        result = answer_question(
            db_path=db_file,
            question=request.q,
            k=request.k,
            citations_limit=request.citations_limit,
            fts=request.fts,
            no_embed=request.no_embed,
            target=request.target,
            embedding_model=request.embedding_model,
            answer_model=request.answer_model,
            synthesis_mode=request.synthesis_mode,
        )
        return _answer_to_schema(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
