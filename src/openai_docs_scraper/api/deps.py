"""Resolve API path defaults from Settings (e.g. DB_PATH in Docker)."""

from __future__ import annotations

from pathlib import Path

from ..services.config import get_settings


def resolve_db_path(explicit: str | None) -> str:
    if explicit is not None and str(explicit).strip() != "":
        return str(Path(explicit).expanduser())
    return str(get_settings().db_path.expanduser())


def resolve_raw_dir(explicit: str | None) -> str:
    if explicit is not None and str(explicit).strip() != "":
        return str(Path(explicit).expanduser())
    return str(get_settings().raw_dir.expanduser())


def resolve_sitemap_path(explicit: str | None) -> str:
    if explicit is not None and str(explicit).strip() != "":
        return str(Path(explicit).expanduser())
    return str(get_settings().sitemap_path.expanduser())
