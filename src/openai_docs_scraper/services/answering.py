"""Grounded answer service built on top of local retrieval."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from ..db import connect, init_db
from ..openai_ops import OpenAIModels, answer_with_citations
from .config import get_settings
from .search import query


def _parse_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class AnswerCitation:
    """A cited evidence item backing a generated answer."""

    index: int
    url: str
    title: Optional[str]
    md_relpath: str
    export_abs_path: Optional[str]
    export_file_exists: bool
    source_path: Optional[str]
    snippet: str
    score: float
    last_seen_at: Optional[str]
    last_seen_run_id: Optional[str]
    content_version: Optional[int]
    stale_summary: bool
    stale_page_embedding: bool


@dataclass(frozen=True)
class AnswerFreshness:
    """Freshness and snapshot metadata for cited evidence."""

    oldest_last_seen_at: Optional[str]
    newest_last_seen_at: Optional[str]
    cited_run_ids: list[str]
    stale_summary_count: int
    stale_page_embedding_count: int
    snapshot_age_days: Optional[float]


@dataclass(frozen=True)
class AnswerResult:
    """Result of grounded answer generation."""

    question: str
    answer: str
    citations: list[AnswerCitation]
    warnings: list[str]
    freshness: AnswerFreshness
    retrieval_target: str
    retrieval_k: int
    retrieval_fts: bool
    retrieval_no_embed: bool
    synthesis_mode: str
    synthesis_model: Optional[str]


def _page_state_by_url(con: sqlite3.Connection, urls: list[str]) -> dict[str, sqlite3.Row]:
    if not urls:
        return {}
    placeholders = ",".join(["?"] * len(urls))
    rows = con.execute(
        f"""
        SELECT url,
               source_path,
               source_hash,
               content_hash,
               content_version,
               last_seen_at,
               last_seen_run_id,
               summary_for_hash,
               embedding_for_hash
        FROM pages
        WHERE url IN ({placeholders});
        """,
        urls,
    ).fetchall()
    return {str(row["url"]): row for row in rows}


def _make_export_path(md_relpath: str) -> tuple[Optional[str], bool]:
    root = get_settings().md_export_root.expanduser().resolve()
    if not md_relpath:
        return None, False
    try:
        path = (root / md_relpath).resolve()
    except OSError:
        return str(root / md_relpath), False
    return str(path), path.is_file()


def _extractive_answer(question: str, citations: list[AnswerCitation]) -> str:
    if not citations:
        return (
            "I could not answer that from the current local snapshot because I did not "
            "find matching documentation evidence."
        )

    lead = "Based on the local snapshot, "
    parts: list[str] = []
    for citation in citations[:2]:
        snippet = " ".join(citation.snippet.split())
        snippet = snippet.rstrip(".")
        parts.append(f"{snippet} [{citation.index}]")

    answer = lead + " ".join(parts)
    if question.strip().endswith("?"):
        return answer
    return answer + "."


def _freshness_from_citations(citations: list[AnswerCitation]) -> AnswerFreshness:
    last_seen_values = [_parse_iso8601(c.last_seen_at) for c in citations if c.last_seen_at]
    last_seen_values = [value for value in last_seen_values if value is not None]
    oldest = min(last_seen_values) if last_seen_values else None
    newest = max(last_seen_values) if last_seen_values else None
    stale_summary_count = sum(1 for c in citations if c.stale_summary)
    stale_page_embedding_count = sum(1 for c in citations if c.stale_page_embedding)
    run_ids = sorted({c.last_seen_run_id for c in citations if c.last_seen_run_id})

    snapshot_age_days: float | None = None
    if newest is not None:
        delta = _utc_now() - newest.astimezone(timezone.utc)
        snapshot_age_days = round(delta.total_seconds() / 86400.0, 2)

    return AnswerFreshness(
        oldest_last_seen_at=oldest.isoformat() if oldest else None,
        newest_last_seen_at=newest.isoformat() if newest else None,
        cited_run_ids=run_ids,
        stale_summary_count=stale_summary_count,
        stale_page_embedding_count=stale_page_embedding_count,
        snapshot_age_days=snapshot_age_days,
    )


def answer_question(
    db_path: str | Path,
    question: str,
    *,
    k: int = 6,
    citations_limit: int = 4,
    fts: bool = True,
    no_embed: bool = False,
    target: Literal["chunks", "pages"] = "chunks",
    embedding_model: Optional[str] = None,
    answer_model: Optional[str] = None,
    synthesis_mode: Literal["auto", "extractive", "openai"] = "auto",
) -> AnswerResult:
    """
    Answer a question from the local docs snapshot with exact citations.

    The answer layer never replaces raw retrieval; it packages the top evidence
    with an answer, freshness metadata, and explicit warnings.
    """
    if answer_model is None:
        answer_model = get_settings().answer_model or OpenAIModels().answer_model

    db_path = Path(db_path)
    hits = query(
        db_path=db_path,
        q=question,
        k=max(k, citations_limit),
        fts=fts,
        no_embed=no_embed,
        group_pages=True,
        embedding_model=embedding_model,
        target=target,
    )

    con = connect(db_path)
    init_db(con)
    urls = [hit.url for hit in hits[:citations_limit]]
    page_state = _page_state_by_url(con, urls)
    con.close()

    citations: list[AnswerCitation] = []
    for index, hit in enumerate(hits[:citations_limit], start=1):
        page = page_state.get(hit.url)
        export_abs_path, export_file_exists = _make_export_path(hit.md_relpath)
        content_hash = page["content_hash"] if page else None
        summary_for_hash = page["summary_for_hash"] if page else None
        embedding_for_hash = page["embedding_for_hash"] if page else None
        citations.append(
            AnswerCitation(
                index=index,
                url=hit.url,
                title=hit.title,
                md_relpath=hit.md_relpath,
                export_abs_path=export_abs_path,
                export_file_exists=export_file_exists,
                source_path=hit.source_path,
                snippet=hit.chunk_text,
                score=hit.score,
                last_seen_at=page["last_seen_at"] if page else None,
                last_seen_run_id=page["last_seen_run_id"] if page else None,
                content_version=int(page["content_version"]) if page and page["content_version"] is not None else None,
                stale_summary=bool(page and summary_for_hash and content_hash and summary_for_hash != content_hash),
                stale_page_embedding=bool(
                    page and embedding_for_hash and summary_for_hash and embedding_for_hash != summary_for_hash
                ),
            )
        )

    freshness = _freshness_from_citations(citations)
    warnings: list[str] = []
    if not citations:
        warnings.append("No matching evidence was found in the current local snapshot.")
    if freshness.stale_summary_count:
        warnings.append(
            f"{freshness.stale_summary_count} stale page summaries were cited relative to the current page content."
        )
    if freshness.stale_page_embedding_count:
        warnings.append(
            f"{freshness.stale_page_embedding_count} stale page embeddings were cited relative to the current summaries."
        )
    if freshness.snapshot_age_days is not None and freshness.snapshot_age_days > 30:
        warnings.append(
            f"The cited snapshot is {freshness.snapshot_age_days} days old; live docs may have changed since then."
        )

    used_mode = synthesis_mode
    if synthesis_mode == "auto":
        used_mode = "openai" if os.getenv("OPENAI_API_KEY") else "extractive"

    if used_mode == "openai" and citations:
        evidence = [
            {
                "index": str(c.index),
                "title": c.title or "(untitled page)",
                "url": c.url,
                "md_relpath": c.md_relpath,
                "snippet": c.snippet,
            }
            for c in citations
        ]
        try:
            answer = answer_with_citations(
                question=question,
                evidence=evidence,
                model=answer_model or OpenAIModels().answer_model,
            )
        except Exception as exc:
            warnings.append(f"OpenAI synthesis failed; falling back to extractive mode: {exc}")
            used_mode = "extractive"
            answer = _extractive_answer(question, citations)
    else:
        answer = _extractive_answer(question, citations)

    return AnswerResult(
        question=question,
        answer=answer,
        citations=citations,
        warnings=warnings,
        freshness=freshness,
        retrieval_target=target,
        retrieval_k=max(k, citations_limit),
        retrieval_fts=fts,
        retrieval_no_embed=no_embed,
        synthesis_mode=used_mode,
        synthesis_model=(answer_model if used_mode == "openai" else None),
    )
