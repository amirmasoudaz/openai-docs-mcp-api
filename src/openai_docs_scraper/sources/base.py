"""Base source adapter interface."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class SourceAdapter:
    """Documentation source adapter contract."""

    name: str
    default_sitemap_url: str

    def normalize_url(self, url: str) -> str:
        """Normalize source URLs so sitemap, DB, and cache entries can be joined."""
        p = urlparse((url or "").strip())
        scheme = (p.scheme or "https").lower()
        netloc = (p.netloc or "").lower()
        path = (p.path or "").rstrip("/") or "/"
        return f"{scheme}://{netloc}{path}"

    def infer_section(self, url: str) -> str | None:
        """Return a source-specific section/grouping key for a page URL."""
        raise NotImplementedError

    def export_relpath(self, url: str) -> Path:
        """Return the canonical markdown export path for a page URL."""
        raise NotImplementedError
