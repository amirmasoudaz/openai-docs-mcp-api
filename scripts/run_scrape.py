#!/usr/bin/env python3
"""Run web scraping job."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path for direct script execution
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openai_docs_scraper.services import run_scrape


def main():
    parser = argparse.ArgumentParser(description="Run web scraping job.")
    parser.add_argument(
        "--db",
        type=str,
        default="data/docs.sqlite3",
        help="Path to the SQLite database (default: data/docs.sqlite3)",
    )
    parser.add_argument(
        "--sitemap",
        type=str,
        default="data/sitemap.xml",
        help="Path to sitemap XML (default: data/sitemap.xml)",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=10,
        help="Maximum number of URLs to scrape (default: 10)",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Starting index in sitemap (default: 0)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Page load timeout in seconds (default: 30.0)",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Don't skip URLs already in database",
    )
    args = parser.parse_args()

    print(f"Starting scrape: {args.limit} URLs from {args.sitemap}")
    print(f"Database: {args.db}")
    print(f"Headless: {args.headless}")
    print()

    result = run_scrape(
        db_path=args.db,
        sitemap_path=args.sitemap,
        limit=args.limit,
        start=args.start,
        headless=args.headless,
        timeout_s=args.timeout,
        skip_existing=not args.no_skip_existing,
    )

    print()
    print("Scrape Results:")
    print(f"  Total URLs:  {result.total_urls}")
    print(f"  Scraped:     {result.scraped}")
    print(f"  Skipped:     {result.skipped}")
    print(f"  Errors:      {result.errors}")

    if result.error_details:
        print("\nErrors:")
        for err in result.error_details:
            print(f"  {err['url']}: {err['error']}")


if __name__ == "__main__":
    main()
