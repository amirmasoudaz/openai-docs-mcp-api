"""Source adapter registry for documentation providers."""

from __future__ import annotations

from .base import SourceAdapter
from .openai_docs import OpenAIDocsSourceAdapter

_SOURCES: dict[str, SourceAdapter] = {
    "openai_docs": OpenAIDocsSourceAdapter(),
}


def get_source(name: str = "openai_docs") -> SourceAdapter:
    """Return the configured source adapter by name."""
    try:
        return _SOURCES[name]
    except KeyError as exc:
        available = ", ".join(sorted(_SOURCES))
        raise ValueError(f"Unknown source adapter {name!r}. Available: {available}") from exc


def list_sources() -> list[str]:
    """Return registered source adapter names."""
    return sorted(_SOURCES)
