#!/usr/bin/env python3
"""Start the OpenAI-docs MCP server.

Usage:
  # stdio (Cursor / Claude Desktop)
  PYTHONPATH=src python scripts/run_mcp.py

  # SSE over HTTP (e.g. for docker or a remote agent)
  PYTHONPATH=src python scripts/run_mcp.py --sse
  PYTHONPATH=src MCP_HOST=0.0.0.0 MCP_PORT=8001 python scripts/run_mcp.py --sse

Environment:
  DB_PATH            Path to SQLite DB       (default: data/docs.sqlite3)
  MD_EXPORT_ROOT     Split markdown root     (default: data/openai_docs_split_rebuilt)
  RAW_DIR            Cached raw JSON root    (default: data/raw_data)
  OPENAI_API_KEY     Required for search     (loaded from .env if present)
  MCP_HOST           Bind host for SSE       (default: 0.0.0.0)
  MCP_PORT           Port for SSE            (default: 8001)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openai_docs_scraper.mcp_server import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the OpenAI-docs MCP server.")
    parser.add_argument(
        "--sse",
        action="store_true",
        help="Use HTTP SSE transport instead of stdio",
    )
    args = parser.parse_args()
    run(transport="sse" if args.sse else "stdio")


if __name__ == "__main__":
    main()
