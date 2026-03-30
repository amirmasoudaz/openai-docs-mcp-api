#!/usr/bin/env python3
"""Generate summaries for pages."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path for direct script execution
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openai_docs_scraper.services import summarize_pages


def main():
    parser = argparse.ArgumentParser(description="Generate summaries for pages.")
    parser.add_argument(
        "--db",
        type=str,
        default="data/docs.sqlite3",
        help="Path to the SQLite database (default: data/docs.sqlite3)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="OpenAI model for summarization (default: gpt-5-nano)",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=50,
        help="Maximum number of pages to summarize (default: 50)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-summarization even if already done",
    )
    parser.add_argument(
        "--section",
        type=str,
        default=None,
        help="Only summarize pages in this section",
    )
    args = parser.parse_args()

    print(f"Summarizing pages from: {args.db}")
    print(f"Model: {args.model or 'gpt-5-nano (default)'}")
    print(f"Limit: {args.limit}")
    if args.section:
        print(f"Section: {args.section}")
    print()

    result = summarize_pages(
        db_path=args.db,
        model=args.model,
        limit=args.limit,
        force=args.force,
        section=args.section,
    )

    print("Summarization Results:")
    print(f"  Total candidates:  {result.total_candidates}")
    print(f"  Updated:           {result.updated}")


if __name__ == "__main__":
    main()
