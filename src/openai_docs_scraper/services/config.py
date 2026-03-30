"""Configuration settings using pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    db_path: Path = Path("data/docs.sqlite3")

    # Sitemap
    sitemap_url: str = "https://platform.openai.com/docs/sitemap.xml"
    sitemap_path: Path = Path("data/sitemap.xml")

    # Raw data directory
    raw_dir: Path = Path("data/raw_data")

    # Split Markdown export (book bundle) — index.md and per-page .md files
    md_export_root: Path = Path("data/openai_docs_split_rebuilt")

    # Browser state
    browser_state_path: Path = Path("data/browser_state.json")

    # OpenAI
    openai_api_key: Optional[str] = None

    # Models
    summary_model: str = "gpt-5-nano"
    embedding_model: str = "text-embedding-3-small"

    # Scraping defaults
    scrape_limit: int = 10
    scrape_timeout_s: float = 30.0
    scrape_headless: bool = False

    # Ingestion defaults
    chunk_max_chars: int = 2500
    chunk_overlap_chars: int = 200

    # Search defaults
    search_k: int = 10


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
