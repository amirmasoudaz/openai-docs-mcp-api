"""Pydantic schemas for API request/response models."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# === Project Schemas ===


class InitProjectRequest(BaseModel):
    """Request to initialize a project database."""

    db_path: Optional[str] = Field(
        default=None,
        description="SQLite path; omit to use DB_PATH / Settings.db_path",
    )


class InitProjectResponse(BaseModel):
    """Response from project initialization."""

    success: bool
    db_path: str


class FetchSitemapRequest(BaseModel):
    """Request to fetch a sitemap."""

    url: str = Field(
        default="https://platform.openai.com/docs/sitemap.xml",
        description="URL of the sitemap to fetch",
    )
    out_path: Optional[str] = Field(
        default=None,
        description="Path to save the sitemap; omit to use Settings.sitemap_path",
    )


class FetchSitemapResponse(BaseModel):
    """Response from sitemap fetch."""

    success: bool
    path: str
    url: str


class SitemapEntry(BaseModel):
    """A single sitemap URL entry."""

    loc: str
    lastmod: Optional[str] = None


class ListSitemapRequest(BaseModel):
    """Request to list sitemap URLs."""

    sitemap_path: Optional[str] = Field(
        default=None,
        description="Path to sitemap XML; omit to use Settings.sitemap_path",
    )
    limit: Optional[int] = Field(default=None, description="Max entries to return")


class ListSitemapResponse(BaseModel):
    """Response from sitemap listing."""

    entries: list[SitemapEntry]
    total: int


# === Scrape Schemas ===


class ScrapeRequest(BaseModel):
    """Request to run scraping."""

    db_path: Optional[str] = Field(default=None, description="Omit to use Settings.db_path")
    sitemap_path: Optional[str] = Field(default=None, description="Omit to use Settings.sitemap_path")
    limit: int = Field(default=10, ge=1)
    start: int = Field(default=0, ge=0)
    headless: bool = Field(default=False)
    timeout_s: float = Field(default=30.0, gt=0)
    skip_existing: bool = Field(default=True)


class ScrapeResponse(BaseModel):
    """Response from scraping."""

    total_urls: int
    scraped: int
    skipped: int
    errors: int
    error_details: list[dict[str, str]]


# === Ingest Schemas ===


class IngestRequest(BaseModel):
    """Request to ingest cached pages."""

    db_path: Optional[str] = Field(default=None, description="Omit to use Settings.db_path")
    raw_dir: Optional[str] = Field(default=None, description="Omit to use Settings.raw_dir")
    limit: Optional[int] = Field(default=None, ge=1)
    force: bool = Field(default=False)
    store_raw_html: bool = Field(default=False)
    store_raw_body_text: bool = Field(default=False)
    chunk_max_chars: int = Field(default=2500, ge=100)
    chunk_overlap_chars: int = Field(default=200, ge=0)


class IngestResponse(BaseModel):
    """Response from ingestion."""

    pages_seen: int
    pages_ingested: int
    chunks_written: int


# === Summarize Schemas ===


class SummarizeRequest(BaseModel):
    """Request to summarize pages."""

    db_path: Optional[str] = Field(default=None, description="Omit to use Settings.db_path")
    model: Optional[str] = Field(default=None, description="OpenAI model for summarization")
    limit: int = Field(default=50, ge=1)
    force: bool = Field(default=False)
    section: Optional[str] = Field(default=None)


class SummarizeResponse(BaseModel):
    """Response from summarization."""

    total_candidates: int
    updated: int


# === Embed Schemas ===


class EmbedRequest(BaseModel):
    """Request to embed pages or chunks."""

    db_path: Optional[str] = Field(default=None, description="Omit to use Settings.db_path")
    target: str = Field(default="chunks", pattern="^(pages|chunks)$")
    model: Optional[str] = Field(default=None, description="OpenAI embedding model")
    limit: int = Field(default=500, ge=1)
    force: bool = Field(default=False)


class EmbedResponse(BaseModel):
    """Response from embedding."""

    total_candidates: int
    updated: int


# === Search Schemas ===


class SearchRequest(BaseModel):
    """Request to search the database."""

    q: str = Field(..., min_length=1, description="Search query")
    db_path: Optional[str] = Field(default=None, description="Omit to use Settings.db_path")
    k: int = Field(default=10, ge=1, le=100)
    fts: bool = Field(default=False, description="Use FTS as pre-filter")
    no_embed: bool = Field(default=False, description="FTS-only search without embeddings")
    group_pages: bool = Field(default=True, description="Return best chunk per page")
    embedding_model: Optional[str] = Field(default=None)
    target: Literal["chunks", "pages"] = Field(
        default="chunks",
        description="Search chunk embeddings or page (summary) embeddings",
    )


class SearchHit(BaseModel):
    """A single search result."""

    url: str
    title: Optional[str]
    summary: Optional[str]
    chunk_text: str
    score: float
    source_path: Optional[str] = None
    md_relpath: str = ""
    export_abs_path: Optional[str] = Field(
        default=None,
        description="Absolute path to the expected split .md under md_export_root",
    )
    export_file_exists: bool = Field(
        default=False,
        description="Whether that .md file exists on disk",
    )


class SearchResponse(BaseModel):
    """Response from search."""

    hits: list[SearchHit]
    query: str
    count: int
    db_path: str = ""
    target: str = "chunks"
    embedding_model: str = ""
    fts: bool = False
    no_embed: bool = False
    group_pages: bool = True


# === Docs reader (index + files) ===


class DocsIndexResponse(BaseModel):
    """Contents of index.md under the Markdown export root."""

    path: str
    content: str
    bytes_length: int


class CatalogEntry(BaseModel):
    """One page row for navigation / tooling."""

    url: str
    title: Optional[str] = None
    section: Optional[str] = None
    summary: Optional[str] = None
    md_relpath: str = ""
    source_path: Optional[str] = None
    has_summary: bool = False
    has_page_embedding: bool = False


class DocsCatalogResponse(BaseModel):
    """All pages known to the database."""

    db_path: str
    count: int
    entries: list[CatalogEntry]


class DocsStatsResponse(BaseModel):
    """Database and export directory stats."""

    db_path: str
    pages_total: int
    pages_with_plain_text: int
    pages_with_summary: int
    pages_with_page_embedding: int
    chunks_total: int
    chunks_with_embedding: int
    md_export_root: str
    index_md_exists: bool
    raw_dir: str


class FileReadResponse(BaseModel):
    """File bytes read from an allowed root (UTF-8 text)."""

    path: str
    root: str
    media_type: str
    content: str
    bytes_length: int

