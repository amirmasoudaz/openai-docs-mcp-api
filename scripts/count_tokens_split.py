#!/usr/bin/env python3
"""Count OpenAI (tiktoken) tokens per split Markdown page; print sorted ascending."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import tiktoken
except ImportError as e:
    print("Install tiktoken: pip install tiktoken", file=sys.stderr)
    raise SystemExit(1) from e


def _get_encoding(model: str | None, encoding_name: str | None):
    if encoding_name:
        return tiktoken.get_encoding(encoding_name)
    if model:
        try:
            return tiktoken.encoding_for_model(model)
        except KeyError:
            pass
    return tiktoken.get_encoding("o200k_base")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Walk a directory of .md files (e.g. data/openai_docs_split), "
            "count tokens with tiktoken, print paths with counts sorted by tokens (ascending)."
        ),
    )
    parser.add_argument(
        "--dir",
        "-d",
        type=str,
        default="data/openai_docs_split",
        help="Root directory containing page .md files (default: data/openai_docs_split)",
    )
    parser.add_argument(
        "--model",
        "-m",
        type=str,
        default="gpt-4o",
        help="Model name for tiktoken.encoding_for_model (default: gpt-4o → o200k_base)",
    )
    parser.add_argument(
        "--encoding",
        "-e",
        type=str,
        default=None,
        metavar="NAME",
        help="Force encoding (e.g. cl100k_base, o200k_base). Overrides --model.",
    )
    parser.add_argument(
        "--include-index",
        action="store_true",
        help="Include index.md in counts (default: skip it)",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Print as CSV: tokens,path",
    )
    args = parser.parse_args()

    root = Path(args.dir).resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        raise SystemExit(1)

    enc = _get_encoding(args.model if not args.encoding else None, args.encoding)

    rows: list[tuple[int, Path]] = []
    for path in sorted(root.rglob("*.md")):
        if not args.include_index and path.name == "index.md":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        n = len(enc.encode(text))
        rows.append((n, path.relative_to(root)))

    rows.sort(key=lambda x: x[0])

    if args.csv:
        print("tokens,path")
        for n, rel in rows:
            print(f"{n},{rel.as_posix()}")
    else:
        w = max(len(str(n)) for n, _ in rows) if rows else 1
        for n, rel in rows:
            print(f"{n:>{w}}  {rel.as_posix()}")
        print()
        enc_label = getattr(enc, "name", None) or args.encoding or args.model
        print(
            f"Files: {len(rows)}  |  Encoding: {enc_label}  |  "
            f"Total tokens: {sum(n for n, _ in rows):,}",
        )


if __name__ == "__main__":
    main()
