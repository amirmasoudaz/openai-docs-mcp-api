#!/usr/bin/env python3
"""Regenerate index.md with title + description for each page under a doc export root."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openai_docs_scraper.page_blurb import write_navigation_index


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dir",
        "-d",
        type=str,
        default="data/openai_docs_split_rebuilt",
        help="Root that contains page .md files and will receive index.md",
    )
    ap.add_argument(
        "--openai",
        action="store_true",
        help="Use OpenAI summarization for blurbs (OPENAI_API_KEY)",
    )
    ap.add_argument(
        "--openai-model",
        type=str,
        default=None,
        help="Summarization model for --openai",
    )
    ap.add_argument(
        "--blurb-max",
        type=int,
        default=240,
        help="Max chars for heuristic blurbs (default: 240)",
    )
    args = ap.parse_args()

    root = Path(args.dir).resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    write_navigation_index(
        root,
        use_openai=args.openai,
        openai_model=args.openai_model,
        max_blurb_chars=args.blurb_max,
    )
    print(f"Wrote {root / 'index.md'}")


if __name__ == "__main__":
    main()
