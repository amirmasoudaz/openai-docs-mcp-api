"""OpenAI Platform docs source adapter."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from .base import SourceAdapter


class OpenAIDocsSourceAdapter(SourceAdapter):
    """Source adapter for `platform.openai.com/docs/...`."""

    def __init__(self) -> None:
        super().__init__(
            name="openai_docs",
            default_sitemap_url="https://platform.openai.com/docs/sitemap.xml",
        )

    def infer_section(self, url: str) -> str | None:
        path = urlparse(url).path
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2 or parts[0] != "docs":
            return None
        return parts[1]

    def export_relpath(self, url: str) -> Path:
        parts = [p for p in urlparse(url).path.strip("/").split("/") if p]
        if parts and parts[0] == "docs":
            parts = parts[1:]
        if not parts:
            parts = ["index"]
        safe: list[str] = []
        for raw in parts:
            s = re.sub(r"[^a-zA-Z0-9._-]", "-", raw).strip("-").lower() or "page"
            safe.append(s)
        return Path(*safe[:-1], f"{safe[-1]}.md")
