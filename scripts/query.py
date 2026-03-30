#!/usr/bin/env python3
"""Execute a search query."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path for direct script execution
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openai_docs_scraper.services import query


def _resolved_path_str(path_str: str | None) -> str:
    if not path_str:
        return "(not recorded)"
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    try:
        return str(p.resolve())
    except OSError:
        return str(p)


def main():
    parser = argparse.ArgumentParser(description="Execute a search query.")
    parser.add_argument(
        "-q", "--query",
        type=str,
        required=True,
        help="Search query",
    )
    parser.add_argument(
        "--db",
        type=str,
        default="data/docs.sqlite3",
        help="Path to the SQLite database (default: data/docs.sqlite3)",
    )
    parser.add_argument(
        "-k",
        type=int,
        default=10,
        help="Number of results (default: 10)",
    )
    parser.add_argument(
        "--fts",
        action="store_true",
        help="Use FTS as pre-filter for vector search",
    )
    parser.add_argument(
        "--no-embed",
        action="store_true",
        help="FTS-only search without embeddings",
    )
    parser.add_argument(
        "--no-group-pages",
        action="store_true",
        help="Don't group results by page (return all chunks)",
    )
    parser.add_argument(
        "--embedding-model",
        type=str,
        default=None,
        help="OpenAI embedding model for query",
    )
    parser.add_argument(
        "--target",
        type=str,
        choices=["chunks", "pages"],
        default="chunks",
        help="Vector space to search: chunk bodies (needs chunk embeddings) or page summaries (needs page embeddings); default: chunks",
    )
    parser.add_argument(
        "--paths",
        action="store_true",
        help="Show raw cache JSON path (from ingest) and split-markdown relative path",
    )
    parser.add_argument(
        "--md-root",
        type=str,
        default=None,
        metavar="DIR",
        help="If set with --paths, also print absolute path under this directory to the .md file (e.g. data/openai_docs_split_rebuilt)",
    )
    args = parser.parse_args()

    hits = query(
        db_path=args.db,
        q=args.query,
        k=args.k,
        fts=args.fts,
        no_embed=args.no_embed,
        group_pages=not args.no_group_pages,
        embedding_model=args.embedding_model,
        target=args.target,
    )

    if not hits:
        print("No results found.")
        return

    print(f"Search Results for: {args.query}")
    print(f"Found {len(hits)} results:\n")

    for i, hit in enumerate(hits, 1):
        print(f"{i}. [{hit.score:.4f}] {hit.url}")
        if hit.title:
            print(f"   Title: {hit.title}")
        if hit.summary:
            print(f"   Summary: {hit.summary}")
        snippet = hit.chunk_text.replace("\n", " ")[:200]
        print(f"   Snippet: {snippet}...")
        if args.paths:
            print(f"   Raw cache: {_resolved_path_str(hit.source_path)}")
            print(f"   Split .md (relative): {hit.md_relpath}")
            if args.md_root:
                md_abs = (Path(args.md_root).expanduser().resolve() / hit.md_relpath)
                print(f"   Split .md (absolute): {md_abs}")
        print()


if __name__ == "__main__":
    main()
