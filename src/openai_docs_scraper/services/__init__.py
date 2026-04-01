"""Service layer for the LLM Provider Docs Ledger."""

from __future__ import annotations

from typing import Any

from .config import Settings, get_settings
from .project import init_project, fetch_sitemap, list_sitemap_urls
from .ingestion import ingest_from_cache, IngestionResult
from .summarizer import summarize_pages, SummarizeResult
from .embedder import embed_pages, embed_chunks, EmbedResult
from .search import query, SearchHit
from .answering import answer_question, AnswerCitation, AnswerFreshness, AnswerResult
from .history import (
    get_page_history,
    diff_page_versions,
    get_run_changes,
    PageHistoryResult,
    PageDiffResult,
    RunChangeReport,
)
from .refresh import run_refresh, RefreshLockedError, RefreshResult

__all__ = [
    "Settings",
    "get_settings",
    "init_project",
    "fetch_sitemap",
    "list_sitemap_urls",
    "run_scrape",
    "ScrapeResult",
    "ingest_from_cache",
    "IngestionResult",
    "summarize_pages",
    "SummarizeResult",
    "embed_pages",
    "embed_chunks",
    "EmbedResult",
    "query",
    "SearchHit",
    "answer_question",
    "AnswerCitation",
    "AnswerFreshness",
    "AnswerResult",
    "get_page_history",
    "diff_page_versions",
    "get_run_changes",
    "PageHistoryResult",
    "PageDiffResult",
    "RunChangeReport",
    "run_refresh",
    "RefreshLockedError",
    "RefreshResult",
]


def __getattr__(name: str) -> Any:
    if name == "run_scrape":
        from .scraper import run_scrape as rs

        return rs
    if name == "ScrapeResult":
        from .scraper import ScrapeResult as SR

        return SR
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(__all__))
