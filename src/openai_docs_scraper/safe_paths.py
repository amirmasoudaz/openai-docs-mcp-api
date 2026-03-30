"""Resolve user-provided relative paths safely under a base directory."""

from __future__ import annotations

from pathlib import Path


class PathOutsideRootError(ValueError):
    """Resolved path would escape the configured root."""


def resolve_under_root(base: Path, relative: str) -> Path:
    """
    Return `base / relative` resolved, ensuring the result stays under `base`.

    Rejects absolute paths, empty paths, and `..` segments.
    """
    rel = (relative or "").strip()
    if not rel:
        raise PathOutsideRootError("path is empty")
    if rel.startswith(("/", "\\")):
        raise PathOutsideRootError("absolute paths are not allowed")

    base_r = base.expanduser().resolve()
    rel_p = Path(rel)
    if ".." in rel_p.parts:
        raise PathOutsideRootError("path traversal is not allowed")

    out = (base_r / rel_p).resolve()
    try:
        out.relative_to(base_r)
    except ValueError as e:
        raise PathOutsideRootError("path escapes base directory") from e
    return out
