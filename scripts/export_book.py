#!/usr/bin/env python3
"""Compile ingested pages into one Markdown book with a table of contents."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openai_docs_scraper.book_export import (
    collect_export_entries,
    export_book_markdown,
    write_book_bundle,
    write_book_monolith,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Export a single Markdown book: sitemap order, TOC by section. "
            "By default includes all data/raw_data JSON caches (not only SQLite)."
        ),
    )
    parser.add_argument(
        "--db",
        type=str,
        default="data/docs.sqlite3",
        help="SQLite database (default: data/docs.sqlite3)",
    )
    parser.add_argument(
        "--sitemap",
        type=str,
        default="data/sitemap.xml",
        help="Sitemap XML for ordering and completeness (default: data/sitemap.xml)",
    )
    parser.add_argument(
        "--out",
        "-o",
        type=str,
        default="data/openai_docs_book.md",
        help="Output Markdown path (default: data/openai_docs_book.md)",
    )
    parser.add_argument(
        "--raw-dir",
        type=str,
        default="data/raw_data",
        help="JSON cache directory (default: data/raw_data). Use empty string to disable.",
    )
    parser.add_argument(
        "--no-raw",
        action="store_true",
        help="Only use SQLite (ignore raw JSON), like the original behavior.",
    )
    parser.add_argument(
        "--include-errors",
        action="store_true",
        help="Include pages with ingest errors (e.g. blocked_or_too_short)",
    )
    parser.add_argument(
        "--split-dir",
        type=str,
        default=None,
        metavar="DIR",
        help=(
            "Also write one .md per page (mirrors /docs/… paths) plus index.md "
            "with relative links for navigation."
        ),
    )
    parser.add_argument(
        "--no-monolith",
        action="store_true",
        help="With --split-dir only: skip writing the single large --out file.",
    )
    args = parser.parse_args()

    raw_dir = None if args.no_raw or not (args.raw_dir or "").strip() else args.raw_dir
    if raw_dir and not Path(raw_dir).is_dir():
        print(f"Warning: raw dir not found ({raw_dir}); export uses SQLite only. ", end="")
        print("Pass --no-raw to silence, or fix --raw-dir.")
        raw_dir = None

    if args.split_dir:
        entries, stats = collect_export_entries(
            db_path=args.db,
            sitemap_path=args.sitemap,
            include_errors=args.include_errors,
            raw_dir=raw_dir,
        )
        if not args.no_monolith:
            write_book_monolith(entries, args.out)
            print(f"Wrote {args.out}")
        write_book_bundle(entries, args.split_dir)
        print(f"Wrote bundle under {args.split_dir}/ (start at index.md)")
    else:
        stats = export_book_markdown(
            db_path=args.db,
            sitemap_path=args.sitemap,
            out_path=args.out,
            include_errors=args.include_errors,
            raw_dir=raw_dir,
        )
        print(f"Wrote {args.out}")

    print(f"  Sitemap URLs:        {stats.sitemap_urls}")
    print(f"  Pages in book:       {stats.pages_in_book}")
    print(f"  Skipped (no source): {stats.skipped_no_source}")
    print(f"  Skipped (errors):    {stats.skipped_errors}")
    print(f"  Raw-only URL tails:  {stats.pages_only_in_raw}")


if __name__ == "__main__":
    main()
