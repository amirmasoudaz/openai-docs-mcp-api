"""MCP server exposing OpenAI docs search and retrieval to AI agents.

Transport: stdio (default) — add --sse to run as SSE server on HTTP.

Tools exposed:
  search_docs          - semantic similarity search over summaries or chunks
  get_doc_file         - read a split .md file (e.g. guides/structured-outputs.md)
  get_page_by_url      - look up a page by its OpenAI docs URL, return content
  get_navigation_index - full index.md (TOC with blurbs for every page)
  get_catalog          - list all pages (url, title, summary, paths)
  get_stats            - DB / export directory stats
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .book_export import rel_md_path_from_url
from .db import connect, init_db
from .safe_paths import PathOutsideRootError, resolve_under_root
from .services.config import get_settings


def _mcp_listen() -> tuple[str, int]:
    """HTTP bind for SSE / streamable-http (stdio ignores these)."""
    host = os.environ.get("MCP_HOST") or os.environ.get("FASTMCP_HOST", "127.0.0.1")
    port_s = os.environ.get("MCP_PORT") or os.environ.get("FASTMCP_PORT", "8001")
    return host, int(port_s)


_mcp_host, _mcp_port = _mcp_listen()

mcp = FastMCP(
    name="openai-docs",
    instructions=(
        "Use these tools to search and read the local mirror of the OpenAI platform "
        "documentation. Always prefer `search_docs` for open-ended questions, then "
        "fetch the full file with `get_doc_file` using the returned `md_relpath`. "
        "Use `get_navigation_index` to orient yourself across all sections."
    ),
    host=_mcp_host,
    port=_mcp_port,
)


# ─── helpers ────────────────────────────────────────────────────────────────


def _settings():
    return get_settings()


def _export_root() -> Path:
    return _settings().md_export_root.expanduser().resolve()


def _raw_root() -> Path:
    return _settings().raw_dir.expanduser().resolve()


def _db_path() -> Path:
    return _settings().db_path.expanduser().resolve()


def _read_md(relpath: str) -> str:
    root = _export_root()
    try:
        p = resolve_under_root(root, relpath)
    except PathOutsideRootError as e:
        raise ValueError(str(e)) from e
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {relpath!r} under {root}")
    return p.read_text(encoding="utf-8")


# ─── tools ──────────────────────────────────────────────────────────────────


@mcp.tool()
def search_docs(
    query: str,
    k: int = 8,
    target: str = "pages",
    fts_prefilter: bool = False,
) -> str:
    """Search the OpenAI documentation by meaning.

    Parameters
    ----------
    query : str
        Natural-language question or keyword phrase.
    k : int
        Number of results to return (1–20, default 8).
    target : str
        Which embedding space to search:
        - "pages" — search over per-page summaries (fast, good for routing).
        - "chunks" — search over document chunks (better for detailed answers).
          Requires chunk embeddings (run `run_embed --target chunks` first).
    fts_prefilter : bool
        When True, first filter candidates via full-text search (BM25) then
        re-rank by embedding similarity. Useful to narrow recall on rare terms.

    Returns
    -------
    JSON string with a list of hits.  Each hit has:
      url, title, summary, score, md_relpath, export_abs_path, export_file_exists.
    """
    from .services.search import query as _query

    k = max(1, min(k, 20))
    tgt = target if target in ("pages", "chunks") else "pages"

    hits = _query(
        db_path=_db_path(),
        q=query,
        k=k,
        fts=fts_prefilter,
        target=tgt,
    )
    export_root = _export_root()
    results = []
    for h in hits:
        exp_abs: str | None = None
        exp_ok = False
        if h.md_relpath:
            p = (export_root / h.md_relpath).resolve()
            exp_abs = str(p)
            exp_ok = p.is_file()
        results.append(
            {
                "url": h.url,
                "title": h.title,
                "summary": h.summary,
                "score": round(h.score, 4),
                "md_relpath": h.md_relpath,
                "export_abs_path": exp_abs,
                "export_file_exists": exp_ok,
                "source_path": h.source_path,
            }
        )
    return json.dumps(results, ensure_ascii=False, indent=2)


@mcp.tool()
def get_doc_file(md_relpath: str) -> str:
    """Read the full Markdown content of a documentation page.

    Parameters
    ----------
    md_relpath : str
        Relative path as returned by `search_docs` or `get_catalog`, e.g.
        "guides/structured-outputs.md" or "models/gpt-4o.md".

    Returns
    -------
    Full UTF-8 Markdown text of the page.
    """
    try:
        return _read_md(md_relpath)
    except FileNotFoundError as e:
        return f"ERROR: {e}"
    except ValueError as e:
        return f"ERROR: {e}"


@mcp.tool()
def get_page_by_url(url: str) -> str:
    """Look up a documentation page by its canonical OpenAI URL and return its content.

    Parameters
    ----------
    url : str
        A URL like "https://platform.openai.com/docs/guides/structured-outputs".

    Returns
    -------
    Full Markdown text of the page, or an error message if not found.
    """
    relpath = rel_md_path_from_url(url).as_posix()
    try:
        return _read_md(relpath)
    except FileNotFoundError:
        return (
            f"ERROR: Page not found in export directory for URL {url!r}.\n"
            f"Expected path: {relpath}\n"
            "Hint: run rebuild_split_markdown to regenerate the export."
        )
    except ValueError as e:
        return f"ERROR: {e}"


@mcp.tool()
def get_navigation_index() -> str:
    """Return the full navigation index (index.md) listing all documentation sections.

    This is the fastest way to orient yourself — it has one line per page with
    the section, filename, title, and a short preview blurb.

    Returns
    -------
    Markdown text of index.md.
    """
    idx = _export_root() / "index.md"
    if not idx.is_file():
        return (
            "ERROR: index.md not found.\n"
            "Hint: run `scripts/refresh_doc_index.py` or "
            "`scripts/rebuild_split_markdown.py --openai-index`."
        )
    return idx.read_text(encoding="utf-8")


@mcp.tool()
def get_catalog(section: Optional[str] = None) -> str:
    """List all documentation pages known to the database.

    Parameters
    ----------
    section : str, optional
        Filter by section name (e.g. "guides", "models", "assistants").
        Omit to return all pages.

    Returns
    -------
    JSON array.  Each item: url, title, section, summary, md_relpath,
    has_summary, has_page_embedding.
    """
    con = connect(_db_path())
    init_db(con)
    if section:
        rows = con.execute(
            """
            SELECT url, title, section, summary,
                   (summary IS NOT NULL AND TRIM(summary) != '') AS has_summary,
                   (embedding IS NOT NULL) AS has_page_embedding
            FROM pages WHERE LOWER(section) = LOWER(?) ORDER BY url;
            """,
            (section,),
        ).fetchall()
    else:
        rows = con.execute(
            """
            SELECT url, title, section, summary,
                   (summary IS NOT NULL AND TRIM(summary) != '') AS has_summary,
                   (embedding IS NOT NULL) AS has_page_embedding
            FROM pages ORDER BY section, url;
            """
        ).fetchall()
    con.close()

    entries = []
    for r in rows:
        url = str(r["url"])
        entries.append(
            {
                "url": url,
                "title": r["title"],
                "section": r["section"],
                "summary": r["summary"],
                "md_relpath": rel_md_path_from_url(url).as_posix(),
                "has_summary": bool(r["has_summary"]),
                "has_page_embedding": bool(r["has_page_embedding"]),
            }
        )
    return json.dumps(entries, ensure_ascii=False, indent=2)


@mcp.tool()
def get_stats() -> str:
    """Return database and export directory statistics.

    Useful for health checks and understanding pipeline state.

    Returns
    -------
    JSON object with page/chunk counts, embedding coverage, and path info.
    """
    db = _db_path()
    export = _export_root()
    raw = _raw_root()

    if not db.is_file():
        return json.dumps({"error": f"database not found: {db}"})

    con = connect(db)
    init_db(con)
    stats = {
        "db_path": str(db),
        "pages_total": int(con.execute("SELECT COUNT(*) FROM pages").fetchone()[0]),
        "pages_with_plain_text": int(
            con.execute(
                "SELECT COUNT(*) FROM pages WHERE plain_text IS NOT NULL AND TRIM(plain_text) != ''"
            ).fetchone()[0]
        ),
        "pages_with_summary": int(
            con.execute(
                "SELECT COUNT(*) FROM pages WHERE summary IS NOT NULL AND TRIM(summary) != ''"
            ).fetchone()[0]
        ),
        "pages_with_page_embedding": int(
            con.execute("SELECT COUNT(*) FROM pages WHERE embedding IS NOT NULL").fetchone()[0]
        ),
        "chunks_total": int(con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]),
        "chunks_with_embedding": int(
            con.execute("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL").fetchone()[0]
        ),
        "md_export_root": str(export),
        "index_md_exists": (export / "index.md").is_file(),
        "raw_dir": str(raw),
    }
    con.close()
    return json.dumps(stats, ensure_ascii=False, indent=2)


# ─── entry point ─────────────────────────────────────────────────────────────


def run(transport: str = "stdio") -> None:
    """Start the MCP server.

    Parameters
    ----------
    transport : str
        "stdio" (default) for Cursor/Claude Desktop integration, or
        "sse"   for HTTP Server-Sent Events (set MCP_HOST / MCP_PORT env vars).
    """
    if transport == "sse":
        # host/port are configured on FastMCP (see _mcp_listen); run() only selects transport.
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    run()
