#!/usr/bin/env python3
"""Initialize the project database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path for direct script execution
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openai_docs_scraper.services import init_project


def main():
    parser = argparse.ArgumentParser(description="Initialize the project database.")
    parser.add_argument(
        "--db",
        type=str,
        default="data/docs.sqlite3",
        help="Path to the SQLite database (default: data/docs.sqlite3)",
    )
    args = parser.parse_args()

    print(f"Initializing database at {args.db}...")
    path = init_project(args.db)
    print(f"✓ Database initialized: {path}")


if __name__ == "__main__":
    main()
