from __future__ import annotations

from .sources import get_source

DEFAULT_SITEMAP_URL = get_source("openai_docs").default_sitemap_url
