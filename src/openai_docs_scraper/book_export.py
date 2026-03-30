"""Build Markdown book(s) from ingested pages: monolith and/or split bundle with index."""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import urlparse

from .db import connect, init_db
from .extract import extract_from_cached_html
from .ingest_cached import CachedPage, iter_cached_pages
from .sitemap import parse_sitemap_xml
from .text import collapse_single_newlines_outside_fences, normalize_whitespace


def normalize_doc_url(url: str) -> str:
    """Align sitemap, DB, and cache URLs (trailing slash, scheme/host case)."""
    p = urlparse((url or "").strip())
    scheme = (p.scheme or "https").lower()
    netloc = (p.netloc or "").lower()
    path = (p.path or "").rstrip("/") or "/"
    return f"{scheme}://{netloc}{path}"


def _anchor_id_for_url(url: str, used: dict[str, int]) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        base = "page"
    else:
        base = "-".join(path.split("/")).lower()
        base = re.sub(r"[^a-z0-9]+", "-", base)
        base = re.sub(r"-+", "-", base).strip("-") or "page"
    n = used.get(base, 0)
    used[base] = n + 1
    return base if n == 0 else f"{base}-{n}"


def rel_md_path_from_url(url: str) -> Path:
    """Path under export root: /docs/guides/foo -> guides/foo.md"""
    parts = [p for p in urlparse(url).path.strip("/").split("/") if p]
    if parts and parts[0] == "docs":
        parts = parts[1:]
    if not parts:
        parts = ["index"]
    safe: list[str] = []
    for raw in parts:
        s = re.sub(r"[^a-zA-Z0-9._-]", "-", raw).strip("-").lower() or "page"
        safe.append(s)
    return Path(*safe).with_suffix(".md")


def _esc_toc_title(title: str) -> str:
    t = " ".join((title or "Untitled").split())
    return t.replace("[", "\\[").replace("]", "\\]")


@dataclass(frozen=True)
class BookExportStats:
    sitemap_urls: int
    pages_in_book: int
    skipped_no_source: int
    skipped_errors: int
    pages_only_in_raw: int


@dataclass(frozen=True)
class ExportEntry:
    url: str
    section: str | None
    title: str | None
    plain_text: str | None
    err: str | None
    anchor: str


def _ingest_style_error(plain: str | None) -> str | None:
    lowered = (plain or "").lower()
    is_blocked = any(
        m in lowered
        for m in (
            "just a moment",
            "waiting for",
            "cloudflare",
            "enable javascript and cookies",
            "signing in",
        )
    )
    is_too_short = len(plain or "") < 300
    if is_blocked or is_too_short:
        return "blocked_or_too_short"
    return None


@dataclass(frozen=True)
class _PreparedPage:
    display_url: str
    section: str | None
    title: str | None
    plain_text: str | None
    err: str | None


def _prepare_page(
    n: str,
    *,
    use_raw: bool,
    by_norm: dict[str, sqlite3.Row],
    cache_by_norm: dict[str, CachedPage],
    norm_to_canon: dict[str, str],
    display_fallback: str,
) -> _PreparedPage | None:
    row = by_norm.get(n)
    cache = cache_by_norm.get(n) if use_raw else None

    if not use_raw:
        if row is None:
            return None
        pu = norm_to_canon.get(n) or str(row["url"])
        return _PreparedPage(
            display_url=pu,
            section=row["section"],
            title=row["title"],
            plain_text=row["plain_text"],
            err=row["error"],
        )

    if cache is None and row is None:
        return None

    err: str | None
    section: str | None
    title: str | None
    plain_text: str | None

    db_ok = (
        row is not None
        and (row["plain_text"] or "").strip()
        and not (row["error"] or "").strip()
    )

    if db_ok:
        err = row["error"]  # type: ignore[union-attr]
        section = row["section"]
        title = row["title"]
        plain_text = row["plain_text"]
    elif cache is not None:
        extracted = extract_from_cached_html(
            url=cache.url,
            title=cache.title,
            raw_html=cache.raw_html,
            raw_body_text=cache.raw_body_text,
            make_markdown=True,
            keep_main_html=True,
        )
        md = (extracted.markdown or "").strip()
        if md:
            plain_text = normalize_whitespace(
                collapse_single_newlines_outside_fences(md),
            )
        else:
            plain_text = normalize_whitespace(extracted.plain_text or "")
        title = extracted.title or cache.title
        section = extracted.section
        err = _ingest_style_error(extracted.plain_text)
        if row is not None and (row["error"] or "").strip() and not err:
            err = row["error"]
    else:
        err = row["error"]  # type: ignore[union-attr]
        section = row["section"]
        title = row["title"]
        plain_text = row["plain_text"]

    display_url = norm_to_canon.get(n) or display_fallback
    if not display_url.startswith("http"):
        if cache is not None:
            display_url = cache.url
        elif row is not None:
            display_url = str(row["url"])

    return _PreparedPage(
        display_url=display_url,
        section=section,
        title=title,
        plain_text=plain_text,
        err=err,
    )


def collect_export_entries(
    *,
    db_path: str | Path,
    sitemap_path: str | Path,
    include_errors: bool = False,
    raw_dir: str | Path | None = None,
) -> tuple[list[ExportEntry], BookExportStats]:
    """Shared sitemap/cache/SQLite resolution → ordered export rows."""
    db_path = Path(db_path)
    sitemap_path = Path(sitemap_path)
    raw_path = Path(raw_dir) if raw_dir else None
    use_raw = raw_path is not None and raw_path.is_dir()

    urls = [u.loc for u in parse_sitemap_xml(sitemap_path.read_bytes())]
    norm_to_canon: dict[str, str] = {}
    for loc in urls:
        norm_to_canon.setdefault(normalize_doc_url(loc), loc)

    con = connect(db_path)
    init_db(con)
    rows = con.execute(
        """
        SELECT url, section, title, plain_text, error
        FROM pages;
        """
    ).fetchall()
    con.close()

    by_norm: dict[str, sqlite3.Row] = {}
    for r in rows:
        by_norm[normalize_doc_url(str(r["url"]))] = r

    cache_by_norm: dict[str, CachedPage] = {}
    if use_raw:
        for page in iter_cached_pages(raw_path):
            n = normalize_doc_url(page.url)
            if n not in cache_by_norm:
                cache_by_norm[n] = page

    entries: list[ExportEntry] = []
    anchor_used: dict[str, int] = {}
    skipped_no_source = 0
    skipped_errors = 0
    seen_norm: set[str] = set()

    def push_if_resolved(n: str, fallback: str) -> None:
        nonlocal skipped_no_source, skipped_errors
        prep = _prepare_page(
            n,
            use_raw=use_raw,
            by_norm=by_norm,
            cache_by_norm=cache_by_norm,
            norm_to_canon=norm_to_canon,
            display_fallback=fallback,
        )
        if prep is None:
            skipped_no_source += 1
            return
        if prep.err and str(prep.err).strip() and not include_errors:
            skipped_errors += 1
            return
        anchor = _anchor_id_for_url(prep.display_url, anchor_used)
        entries.append(
            ExportEntry(
                url=prep.display_url,
                section=prep.section,
                title=prep.title,
                plain_text=prep.plain_text,
                err=prep.err,
                anchor=anchor,
            )
        )
        seen_norm.add(n)

    for loc in urls:
        n = normalize_doc_url(loc)
        if n in seen_norm:
            continue
        push_if_resolved(n, loc)

    pages_only_in_raw = 0
    if use_raw:
        tail = sorted(set(cache_by_norm.keys()) - seen_norm)
        pages_only_in_raw = len(tail)
        for n in tail:
            cache = cache_by_norm[n]
            push_if_resolved(n, cache.url)

    stats = BookExportStats(
        sitemap_urls=len(urls),
        pages_in_book=len(entries),
        skipped_no_source=skipped_no_source,
        skipped_errors=skipped_errors,
        pages_only_in_raw=pages_only_in_raw,
    )
    return entries, stats


def write_book_monolith(entries: list[ExportEntry], out_path: str | Path) -> None:
    """Write single-file book from pre-built entries."""
    out_path = Path(out_path)
    section_order: list[str] = []
    section_pages: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for e in entries:
        sec = e.section or "other"
        if sec not in section_order:
            section_order.append(sec)
        section_pages[sec].append((e.anchor, _esc_toc_title(e.title or e.url)))

    lines: list[str] = [
        "# OpenAI platform documentation (compiled)",
        "",
        f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC · {len(entries)} pages_",
        "",
        "## Table of contents",
        "",
    ]

    for sec in section_order:
        lines.append(f"### {sec}")
        lines.append("")
        for anchor, toc_title in section_pages[sec]:
            lines.append(f"- [{toc_title}](#{anchor})")
        lines.append("")

    lines.extend(["---", ""])

    for e in entries:
        h2 = (e.title or "Untitled").strip() or e.url
        lines.append(f'<h2 id="{e.anchor}">{escape(h2)}</h2>')
        lines.append("")
        lines.append(f"**Section:** `{e.section or '—'}`  ")
        lines.append(f"**Source:** {e.url}")
        if e.err:
            lines.append(f"**Ingest note:** `{e.err}`")
        lines.append("")
        body = (e.plain_text or "").strip()
        if body:
            lines.append(body)
        else:
            lines.append("_(No plain text for this page.)_")
        lines.extend(["", "---", ""])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_book_bundle(entries: list[ExportEntry], out_dir: str | Path) -> None:
    """Write split tree + index.md from pre-built entries."""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)

    path_claim: dict[str, str] = {}
    section_order: list[str] = []
    section_pages: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for e in entries:
        rel = rel_md_path_from_url(e.url)
        key = rel.as_posix()
        if key in path_claim and path_claim[key] != e.url:
            stem = rel.stem
            suf = 2
            while True:
                cand = rel.with_name(f"{stem}-{suf}.md")
                k = cand.as_posix()
                if k not in path_claim:
                    rel = cand
                    key = k
                    break
                suf += 1
        path_claim[key] = e.url

        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        h1 = (e.title or "Untitled").strip() or e.url
        parts = [
            f"# {h1}",
            "",
            f"**Section:** `{e.section or '—'}`  ",
            f"**Source:** {e.url}",
        ]
        if e.err:
            parts.append(f"**Ingest note:** `{e.err}`")
        parts.extend(["", (e.plain_text or "").strip() or "_(No plain text for this page.)_"])
        dest.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")

        sec = e.section or "other"
        if sec not in section_order:
            section_order.append(sec)
        section_pages[sec].append((rel.as_posix(), _esc_toc_title(e.title or e.url)))

    index_lines = [
        "# OpenAI platform docs — navigation index",
        "",
        "_Open `index.md` and use relative links below (works in any Markdown viewer)._",
        "",
        f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC · {len(entries)} pages_",
        "",
        "## By section",
        "",
    ]
    for sec in section_order:
        index_lines.append(f"### {sec}")
        index_lines.append("")
        for rel_path, toc_title in section_pages[sec]:
            index_lines.append(f"- [{toc_title}]({rel_path})")
        index_lines.append("")

    (root / "index.md").write_text("\n".join(index_lines).rstrip() + "\n", encoding="utf-8")


def export_book_markdown(
    *,
    db_path: str | Path,
    sitemap_path: str | Path,
    out_path: str | Path,
    include_errors: bool = False,
    raw_dir: str | Path | None = None,
) -> BookExportStats:
    """
    Single file: TOC with fragment links, then chapters.

    Headings use ``<h2 id="slug">…</h2>`` so Ctrl+click works in VS Code and
    other previews that ignore orphan ``<a id>`` or only slug headings.
    """
    entries, stats = collect_export_entries(
        db_path=db_path,
        sitemap_path=sitemap_path,
        include_errors=include_errors,
        raw_dir=raw_dir,
    )
    write_book_monolith(entries, out_path)
    return stats


def export_book_bundle(
    *,
    db_path: str | Path,
    sitemap_path: str | Path,
    out_dir: str | Path,
    include_errors: bool = False,
    raw_dir: str | Path | None = None,
) -> BookExportStats:
    """
    One Markdown file per doc URL path (mirrors /docs/… as folders) plus
    ``index.md`` with relative links for reliable navigation in any viewer.
    """
    entries, stats = collect_export_entries(
        db_path=db_path,
        sitemap_path=sitemap_path,
        include_errors=include_errors,
        raw_dir=raw_dir,
    )
    write_book_bundle(entries, out_dir)
    return stats
