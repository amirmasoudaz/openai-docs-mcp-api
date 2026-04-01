#!/usr/bin/env python3
"""Run a tracked refresh and publish a new SQLite snapshot on success."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openai_docs_scraper.services import RefreshLockedError, run_refresh


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=str, default="data/docs.sqlite3", help="SQLite database path")
    parser.add_argument("--raw-dir", type=str, default="data/raw_data", help="Raw JSON cache directory")
    parser.add_argument("--sitemap", type=str, default="data/sitemap.xml", help="Local sitemap path")
    parser.add_argument("--sitemap-url", type=str, default=None, help="Override sitemap URL")
    parser.add_argument("--trigger", type=str, default="manual", help="Run trigger label (manual, scheduled, cron, etc.)")
    parser.add_argument("--lock-path", type=str, default=None, help="Override refresh lock file path")
    parser.add_argument("--lock-timeout-s", type=int, default=None, help="Treat lock as stale after this many seconds")
    parser.add_argument("--log-path", type=str, default=None, help="Append JSONL refresh logs to this path")
    parser.add_argument(
        "--no-fetch-sitemap",
        action="store_true",
        help="Reuse the existing local sitemap instead of downloading a fresh one",
    )
    parser.add_argument("--limit", type=int, default=None, help="Maximum cached pages to ingest")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Do not mark pages missing from the current raw cache as deleted",
    )
    parser.add_argument("--force", action="store_true", help="Force re-ingestion of unchanged pages")
    parser.add_argument("--store-raw-html", action="store_true", help="Persist raw HTML in SQLite")
    parser.add_argument("--store-raw-body-text", action="store_true", help="Persist raw body text in SQLite")
    parser.add_argument("--chunk-max-chars", type=int, default=None, help="Chunk size override")
    parser.add_argument("--chunk-overlap-chars", type=int, default=None, help="Chunk overlap override")
    args = parser.parse_args()

    try:
        result = run_refresh(
            db_path=args.db,
            raw_dir=args.raw_dir,
            sitemap_path=args.sitemap,
            sitemap_url=args.sitemap_url,
            fetch_latest_sitemap=not args.no_fetch_sitemap,
            trigger=args.trigger,
            limit=args.limit,
            mark_missing_deleted=not args.incremental,
            force=args.force,
            store_raw_html=args.store_raw_html,
            store_raw_body_text=args.store_raw_body_text,
            chunk_max_chars=args.chunk_max_chars,
            chunk_overlap_chars=args.chunk_overlap_chars,
            lock_path=args.lock_path,
            lock_timeout_s=args.lock_timeout_s,
            log_path=args.log_path,
        )
    except RefreshLockedError as exc:
        print(f"Refresh skipped: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"Refresh failed: {exc}", file=sys.stderr)
        return 1

    print("Refresh Result:")
    print(f"  Source:        {result.source_name}")
    print(f"  Run ID:        {result.run_id}")
    print(f"  Snapshot ID:   {result.snapshot_id}")
    print(f"  Status:        {result.status}")
    print(f"  Started:       {result.started_at}")
    print(f"  Finished:      {result.finished_at}")
    print(f"  Database:      {result.db_path}")
    print(f"  Sitemap:       {result.sitemap_path}")
    print(f"  Pages total:   {result.pages_total}")
    print(f"  Chunks total:  {result.chunks_total}")
    print(f"  Pages seen:    {result.pages_seen}")
    print(f"  Pages new:     {result.pages_new}")
    print(f"  Pages changed: {result.pages_changed}")
    print(f"  Pages deleted: {result.pages_deleted}")
    print(f"  Pages failed:  {result.pages_failed}")
    print(f"  Unchanged:     {result.pages_unchanged}")
    print(f"  Chunks wrote:  {result.chunks_written}")
    print(f"  Exports stale: {result.exports_invalidated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
