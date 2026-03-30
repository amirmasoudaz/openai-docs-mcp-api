#!/usr/bin/env python3
"""
Rebuild split Markdown pages as clean Markdown by re-extracting from raw HTML.

Why not "polish" the existing .md files?
  Those files are flattened text from markdownify; code blocks and structure are
  often missing. Re-running extract_from_cached_html() on data/raw_data JSON is
  the same source of truth as the original bundle export and preserves content
  relative to the HTML (no summarization).

Walks --input-dir (e.g. data/openai_docs_split), reads **Source:** URL from each
page, loads matching cache JSON, writes to --out-dir with the same layout as
export_book_bundle (path from URL).

Batches: use --start / --limit to process chunks in a long job.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openai_docs_scraper.book_export import normalize_doc_url, rel_md_path_from_url
from openai_docs_scraper.extract import extract_from_cached_html
from openai_docs_scraper.page_blurb import write_navigation_index
from openai_docs_scraper.text import collapse_single_newlines_outside_fences, normalize_whitespace

SOURCE_RE = re.compile(r"^\*\*Source:\*\*\s*(\S+)", re.MULTILINE)
SECTION_RE = re.compile(r"^\*\*Section:\*\*\s*`([^`]*)`", re.MULTILINE)


def _ingest_style_error(plain: str | None) -> str | None:
    lowered = (plain or "").lower()
    if any(
        m in lowered
        for m in (
            "just a moment",
            "waiting for",
            "cloudflare",
            "enable javascript and cookies",
            "signing in",
        )
    ):
        return "blocked_or_too_short"
    if len(plain or "") < 300:
        return "blocked_or_too_short"
    return None


def parse_split_header(md: str) -> tuple[str | None, str | None, str | None]:
    """From an existing split file: (# title text, section, source url)."""
    title = None
    for line in md.splitlines()[:40]:
        if line.startswith("# "):
            title = line[2:].strip()
            break
    sm = SECTION_RE.search(md)
    section = sm.group(1).strip() if sm else None
    um = SOURCE_RE.search(md)
    source = um.group(1).rstrip(")") if um else None
    return title, section, source


def index_raw_json(raw_dir: Path) -> dict[str, Path]:
    """Map normalized URL -> json path (last file wins if duplicates)."""
    idx: dict[str, Path] = {}
    for p in sorted(raw_dir.glob("*.json")):
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        url = (obj.get("url") or "").strip()
        if not url:
            continue
        idx[normalize_doc_url(url)] = p
    return idx


def _strip_leading_duplicate_h1(body: str, h1: str) -> str:
    """Remove a leading # line if it matches the page title (markdownify repeats title)."""
    h1 = (h1 or "").strip()
    if not h1 or not body.strip():
        return body
    lines = body.splitlines()
    if not lines:
        return body
    first = lines[0].strip()
    if not first.startswith("# "):
        return body
    rest = first[2:].strip()
    if rest != h1 and rest.lower() != h1.lower():
        return body
    i = 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    return "\n".join(lines[i:])


def body_from_raw_json(path: Path) -> tuple[str, str | None, str | None, str | None]:
    """
    Returns (markdown_body, title, section, err_note).
    err_note is blocked_or_too_short when extraction looks bad.
    """
    obj = json.loads(path.read_text(encoding="utf-8"))
    url = (obj.get("url") or "").strip()
    extracted = extract_from_cached_html(
        url=url,
        title=obj.get("title"),
        raw_html=obj.get("raw") or "",
        raw_body_text=obj.get("body"),
        make_markdown=True,
        keep_main_html=True,
    )
    md = (extracted.markdown or "").strip()
    if md:
        body = normalize_whitespace(collapse_single_newlines_outside_fences(md))
    else:
        body = normalize_whitespace(extracted.plain_text or "")
    err = _ingest_style_error(extracted.plain_text)
    title = extracted.title or obj.get("title")
    section = extracted.section
    if title:
        body = _strip_leading_duplicate_h1(body, str(title))
    return body, title, section, err


def format_page(
    *,
    h1_title: str,
    section: str | None,
    source_url: str,
    body: str,
    err: str | None,
) -> str:
    lines = [
        f"# {h1_title}",
        "",
        f"**Section:** `{section or '—'}`  ",
        f"**Source:** {source_url}",
    ]
    if err:
        lines.append(f"**Ingest note:** `{err}`")
    lines.extend(["", body.strip() if body else "_(No body extracted.)_"])
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--input-dir",
        "-i",
        type=str,
        default="data/openai_docs_split",
        help="Existing split export (reads **Source:** from each page)",
    )
    ap.add_argument(
        "--out-dir",
        "-o",
        type=str,
        default="data/openai_docs_split_rebuilt",
        help="Output root (mirrors URL paths as .md files)",
    )
    ap.add_argument(
        "--raw-dir",
        type=str,
        default="data/raw_data",
        help="Directory of crawl JSON caches",
    )
    ap.add_argument(
        "--start",
        type=int,
        default=0,
        help="Skip first N files after sorting (batching)",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N files (after --start)",
    )
    ap.add_argument(
        "--no-index",
        action="store_true",
        help="Do not write index.md at the end",
    )
    ap.add_argument(
        "--copy-on-miss",
        action="store_true",
        help="If no raw JSON for a URL, copy the input .md unchanged",
    )
    ap.add_argument(
        "--openai-index",
        action="store_true",
        help="Use OpenAI to summarize each page for index blurbs (needs OPENAI_API_KEY)",
    )
    ap.add_argument(
        "--openai-model",
        type=str,
        default=None,
        help="Model for --openai-index (default: OpenAIModels.summary_model)",
    )
    ap.add_argument(
        "--blurb-max",
        type=int,
        default=240,
        help="Max chars for heuristic blurbs when not using --openai-index (default: 240)",
    )
    args = ap.parse_args()

    input_dir = Path(args.input_dir).resolve()
    out_root = Path(args.out_dir).resolve()
    raw_dir = Path(args.raw_dir).resolve()

    if not input_dir.is_dir():
        print(f"Missing input dir: {input_dir}", file=sys.stderr)
        sys.exit(1)
    if not raw_dir.is_dir():
        print(f"Missing raw dir: {raw_dir}", file=sys.stderr)
        sys.exit(1)

    raw_index = index_raw_json(raw_dir)
    print(f"Indexed {len(raw_index)} URLs from {raw_dir}", flush=True)

    md_files = sorted(
        p for p in input_dir.rglob("*.md") if p.name != "index.md"
    )
    md_files = md_files[args.start :]
    if args.limit is not None:
        md_files = md_files[: args.limit]

    out_root.mkdir(parents=True, exist_ok=True)

    ok = 0
    missing_raw = 0
    errors = 0

    for i, md_path in enumerate(md_files, 1):
        text = md_path.read_text(encoding="utf-8", errors="replace")
        old_title, old_section, source = parse_split_header(text)
        if not source:
            print(f"[skip] no Source URL: {md_path.relative_to(input_dir)}", flush=True)
            errors += 1
            continue

        key = normalize_doc_url(source)
        jp = raw_index.get(key)
        rel_out = rel_md_path_from_url(source)
        dest = out_root / rel_out

        if jp is None:
            missing_raw += 1
            if args.copy_on_miss:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(text, encoding="utf-8")
                ok += 1
            else:
                print(f"[miss] no raw JSON for {key}", flush=True)
            continue

        try:
            body, title, section, err = body_from_raw_json(jp)
        except Exception as e:
            print(f"[err] {md_path}: {e}", flush=True)
            errors += 1
            continue

        h1 = (title or old_title or "Untitled").strip()
        sec = section if section is not None else old_section
        page = format_page(
            h1_title=h1,
            section=sec,
            source_url=key,
            body=body,
            err=err,
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(page, encoding="utf-8")
        ok += 1

        if i % 25 == 0 or i == len(md_files):
            print(f"  … {i}/{len(md_files)} written (last: {rel_out.as_posix()})", flush=True)

    if not args.no_index:
        write_navigation_index(
            out_root,
            use_openai=args.openai_index,
            openai_model=args.openai_model,
            max_blurb_chars=args.blurb_max,
            intro_extra="_Paths match URL layout under platform.openai.com/docs/…_",
        )

    print()
    print(f"Done. Wrote {ok} page(s) under {out_root}")
    print(f"  Missing raw cache (skipped unless --copy-on-miss): {missing_raw}")
    print(f"  Skipped/errors: {errors}")


if __name__ == "__main__":
    main()
