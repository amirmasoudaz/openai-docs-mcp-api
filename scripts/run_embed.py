#!/usr/bin/env python3
"""Generate embeddings for pages or chunks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path for direct script execution
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openai_docs_scraper.services import embed_pages, embed_chunks


def main():
    parser = argparse.ArgumentParser(description="Generate embeddings for pages or chunks.")
    parser.add_argument(
        "--db",
        type=str,
        default="data/docs.sqlite3",
        help="Path to the SQLite database (default: data/docs.sqlite3)",
    )
    parser.add_argument(
        "--target",
        type=str,
        choices=["pages", "chunks"],
        default="chunks",
        help="What to embed: pages or chunks (default: chunks)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="OpenAI embedding model (default: text-embedding-3-small)",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=500,
        help="Maximum number of items to embed (default: 500)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-embedding even if already done",
    )
    args = parser.parse_args()

    print(f"Embedding {args.target} from: {args.db}")
    print(f"Model: {args.model or 'text-embedding-3-small (default)'}")
    print(f"Limit: {args.limit}")
    print()

    if args.target == "pages":
        result = embed_pages(
            db_path=args.db,
            model=args.model,
            limit=args.limit,
            force=args.force,
        )
    else:
        result = embed_chunks(
            db_path=args.db,
            model=args.model,
            limit=args.limit,
            force=args.force,
        )

    print("Embedding Results:")
    print(f"  Total candidates:  {result.total_candidates}")
    print(f"  Updated:           {result.updated}")


if __name__ == "__main__":
    main()
