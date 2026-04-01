"""Scraping service."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..db import connect, init_db, upsert_page
from ..sources import get_source
from ..selenium_fetcher import SeleniumChromeFetcher
from ..sitemap import parse_sitemap_xml
from .config import get_settings


@dataclass
class ScrapeResult:
    """Result of a scrape operation."""

    total_urls: int = 0
    scraped: int = 0
    skipped: int = 0
    errors: int = 0
    error_details: list[dict[str, str]] = field(default_factory=list)


def run_scrape(
    db_path: str | Path,
    sitemap_path: str | Path,
    *,
    limit: int = 10,
    start: int = 0,
    headless: bool = False,
    timeout_s: float = 30.0,
    skip_existing: bool = True,
) -> ScrapeResult:
    """
    Run a scraping job.

    Args:
        db_path: Path to the SQLite database.
        sitemap_path: Path to the sitemap XML file.
        limit: Maximum number of URLs to scrape.
        start: Starting index in the sitemap.
        headless: Run browser in headless mode.
        timeout_s: Page load timeout in seconds.
        skip_existing: Skip URLs already in the database.

    Returns:
        ScrapeResult with statistics.
    """
    db_path = Path(db_path)
    sitemap_path = Path(sitemap_path)
    source = get_source(get_settings().source_name)

    urls = [u.loc for u in parse_sitemap_xml(sitemap_path.read_bytes())]
    urls = urls[start : start + limit]

    result = ScrapeResult(total_urls=len(urls))

    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = connect(db_path)
    init_db(con)

    existing: set[str] = set()
    if skip_existing:
        existing = {r["url"] for r in con.execute("SELECT url FROM pages").fetchall()}

    with SeleniumChromeFetcher(headless=headless) as fetcher:
        for url in urls:
            if skip_existing and url in existing:
                result.skipped += 1
                continue

            page = fetcher.fetch(url, timeout_s=timeout_s)

            if page.error:
                result.errors += 1
                result.error_details.append({"url": url, "error": page.error})
            else:
                result.scraped += 1

            upsert_page(
                con,
                url=page.url,
                section=source.infer_section(page.url),
                title=page.title,
                raw_html=page.raw_html,
                raw_body_text=None,
                main_html=page.main_html,
                plain_text=page.main_text,
                content_hash=page.content_hash,
                scraped_at=page.scraped_at,
                ingested_at=None,
                source_path=None,
                source_hash=None,
                http_status=200 if page.error is None else None,
                error=page.error,
                content_version=1,
                changed_at=page.scraped_at,
                page_state="failed" if page.error else None,
                last_seen_at=None,
                last_seen_run_id=None,
                deleted_at=None,
                deletion_reason=None,
            )

    con.close()
    return result
