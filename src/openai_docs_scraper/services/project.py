"""Project initialization and sitemap services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from ..constants import DEFAULT_SITEMAP_URL
from ..db import connect, init_db
from ..sitemap import parse_sitemap_xml


@dataclass(frozen=True)
class SitemapEntry:
    """A single sitemap URL entry."""

    loc: str
    lastmod: Optional[str] = None


def init_project(db_path: str | Path) -> Path:
    """
    Initialize the project database.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Path to the created database.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = connect(db_path)
    init_db(con)
    con.close()
    return db_path


def fetch_sitemap(
    out_path: str | Path,
    url: str = DEFAULT_SITEMAP_URL,
    timeout: float = 60.0,
) -> Path:
    """
    Fetch sitemap XML and save to disk.

    Args:
        out_path: Path to save the sitemap XML.
        url: URL of the sitemap.
        timeout: HTTP timeout in seconds.

    Returns:
        Path to the saved sitemap file.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        resp = client.get(url)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
    return out_path


def list_sitemap_urls(
    sitemap_path: str | Path,
    limit: Optional[int] = None,
) -> list[SitemapEntry]:
    """
    Parse sitemap and return URL entries.

    Args:
        sitemap_path: Path to the sitemap XML file.
        limit: Maximum number of entries to return (None for all).

    Returns:
        List of SitemapEntry objects.
    """
    sitemap_path = Path(sitemap_path)
    raw_entries = parse_sitemap_xml(sitemap_path.read_bytes())
    entries = [SitemapEntry(loc=e.loc, lastmod=getattr(e, "lastmod", None)) for e in raw_entries]
    if limit is not None:
        entries = entries[:limit]
    return entries
