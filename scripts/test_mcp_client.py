#!/usr/bin/env python3
"""Exercise the MCP server over SSE (Docker docs-mcp) or stdio (local run_mcp.py).

Examples:
  # HTTP SSE (server must be up: docker compose up docs-mcp)
  PYTHONPATH=src .venv/bin/python scripts/test_mcp_client.py --url http://127.0.0.1:8001/sse

  # stdio (starts subprocess — same as Cursor)
  PYTHONPATH=src .venv/bin/python scripts/test_mcp_client.py --stdio

  # Call a specific tool
  PYTHONPATH=src .venv/bin/python scripts/test_mcp_client.py --url http://127.0.0.1:8001/sse \\
    --tool get_stats
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import anyio
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client


def _text_from_result(result: types.CallToolResult) -> str:
    parts: list[str] = []
    for block in result.content:
        if isinstance(block, types.TextContent):
            parts.append(block.text)
        else:
            parts.append(str(block))
    return "\n".join(parts) if parts else "(no text content)"


async def run_sse(url: str, tool: str | None, tool_args: dict) -> None:
    print(f"Connecting to SSE: {url}", file=sys.stderr)
    async with sse_client(url) as streams:
        read, write = streams
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = [t.name for t in listed.tools]
            print("Tools:", ", ".join(names), file=sys.stderr)
            if tool:
                result = await session.call_tool(tool, tool_args)
                if result.isError:
                    print("Error:", _text_from_result(result), file=sys.stderr)
                    sys.exit(1)
                print(_text_from_result(result))
            else:
                result = await session.call_tool(
                    "search_docs",
                    {"query": "structured outputs", "k": 3, "target": "pages"},
                )
                if result.isError:
                    print("Error:", _text_from_result(result), file=sys.stderr)
                    sys.exit(1)
                print(_text_from_result(result))


async def run_stdio(py: str, script: str, tool: str | None, tool_args: dict) -> None:
    repo = Path(__file__).parent.parent
    env = {
        **dict(__import__("os").environ),
        "PYTHONPATH": str(repo / "src"),
    }
    params = StdioServerParameters(
        command=py,
        args=[str(script)],
        env=env,
    )
    print("Starting MCP via stdio…", file=sys.stderr)
    async with stdio_client(params) as streams:
        read, write = streams
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            print("Tools:", ", ".join(t.name for t in listed.tools), file=sys.stderr)
            if tool:
                result = await session.call_tool(tool, tool_args)
            else:
                result = await session.call_tool(
                    "get_stats",
                    {},
                )
            if result.isError:
                print("Error:", _text_from_result(result), file=sys.stderr)
                sys.exit(1)
            print(_text_from_result(result))


def main() -> None:
    parser = argparse.ArgumentParser(description="Test openai-docs MCP server.")
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="SSE endpoint (e.g. http://127.0.0.1:8001/sse)",
    )
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Talk to local scripts/run_mcp.py over stdio (no HTTP)",
    )
    parser.add_argument(
        "--tool",
        type=str,
        default=None,
        help="Tool name to call (default: search_docs for --url, get_stats for --stdio)",
    )
    parser.add_argument(
        "--args",
        type=str,
        default="{}",
        help='JSON object for tool arguments, e.g. \'{"query":"batch","k":5}\'',
    )
    parser.add_argument(
        "--python",
        type=str,
        default=sys.executable,
        help="Python for --stdio subprocess",
    )
    args = parser.parse_args()

    try:
        tool_args = json.loads(args.args) if args.args else {}
    except json.JSONDecodeError as e:
        print("--args must be valid JSON:", e, file=sys.stderr)
        sys.exit(2)

    if args.stdio:
        repo = Path(__file__).parent.parent
        script = repo / "scripts" / "run_mcp.py"
        tool = args.tool or "get_stats"

        async def _stdio_main():
            await run_stdio(args.python, str(script), tool, tool_args)

        anyio.run(_stdio_main, backend="asyncio")
        return

    if args.url:
        if urlparse(args.url).scheme not in ("http", "https"):
            print("--url must be http(s)", file=sys.stderr)
            sys.exit(2)
        tool = args.tool  # None => default search_docs in run_sse

        async def _sse_main():
            await run_sse(args.url, tool, tool_args)

        anyio.run(_sse_main, backend="asyncio")
        return

    parser.error("Pass --url http://127.0.0.1:8001/sse or --stdio")


if __name__ == "__main__":
    main()
