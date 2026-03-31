#!/usr/bin/env python3
"""Ingest cached pages into the database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path for direct script execution
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openai_docs_scraper.services import ingest_from_cache


def main():
    parser = argparse.ArgumentParser(description="Ingest cached pages into the database.")
    parser.add_argument(
        "--db",
        type=str,
        default="data/docs.sqlite3",
        help="Path to the SQLite database (default: data/docs.sqlite3)",
    )
    parser.add_argument(
        "--raw-dir",
        type=str,
        default="data/raw_data",
        help="Directory containing raw JSON cache files (default: data/raw_data)",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=None,
        help="Maximum number of pages to ingest (default: all)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--incremental",
        action="store_true",
        help="Do not mark pages missing from the current raw cache as deleted",
    )
    mode.add_argument(
        "--full-refresh",
        action="store_true",
        help="Mark pages missing from the current raw cache as deleted (default behavior)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-ingestion even if content unchanged",
    )
    parser.add_argument(
        "--store-raw-html",
        action="store_true",
        help="Store full raw HTML in database",
    )
    parser.add_argument(
        "--store-raw-body-text",
        action="store_true",
        help="Store raw body text in database",
    )
    parser.add_argument(
        "--chunk-max-chars",
        type=int,
        default=2500,
        help="Maximum characters per chunk (default: 2500)",
    )
    parser.add_argument(
        "--chunk-overlap-chars",
        type=int,
        default=200,
        help="Overlap between chunks (default: 200)",
    )
    args = parser.parse_args()

    print(f"Ingesting from: {args.raw_dir}")
    print(f"Database: {args.db}")
    if args.limit:
        print(f"Limit: {args.limit}")
    print(f"Mode: {'incremental' if args.incremental else 'full_refresh'}")
    print()

    result = ingest_from_cache(
        db_path=args.db,
        raw_dir=args.raw_dir,
        limit=args.limit,
        mark_missing_deleted=not args.incremental,
        force=args.force,
        store_raw_html=args.store_raw_html,
        store_raw_body_text=args.store_raw_body_text,
        chunk_max_chars=args.chunk_max_chars,
        chunk_overlap_chars=args.chunk_overlap_chars,
    )

    print("Ingestion Results:")
    print(f"  Pages seen:      {result.pages_seen}")
    print(f"  Pages ingested:  {result.pages_ingested}")
    print(f"  Pages unchanged: {result.pages_unchanged}")
    print(f"  Pages new:       {result.pages_new}")
    print(f"  Pages changed:   {result.pages_changed}")
    print(f"  Pages deleted:   {result.pages_deleted}")
    print(f"  Chunks written:  {result.chunks_written}")
    print(f"  Summaries stale: {result.summaries_invalidated}")
    print(f"  Page embeds stale: {result.page_embeddings_invalidated}")
    print(f"  Chunk embeds stale: {result.chunk_embeddings_invalidated}")


if __name__ == "__main__":
    main()
