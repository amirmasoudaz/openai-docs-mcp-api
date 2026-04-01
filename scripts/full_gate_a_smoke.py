#!/usr/bin/env python3
"""Local smoke gate for API, retrieval, grounded answers, docs, and MCP surfaces."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import anyio

from openai_docs_scraper.api.main import app_config, health_check
from openai_docs_scraper.api.routes.docs import get_changes as api_get_changes
from openai_docs_scraper.api.routes.docs import get_stats as api_docs_stats
from openai_docs_scraper.api.routes.search import api_answer_post, api_search_post
from openai_docs_scraper.api.schemas import AnswerRequest, SearchRequest
from openai_docs_scraper.mcp_server import answer_question as mcp_answer_question
from openai_docs_scraper.mcp_server import get_recent_changes as mcp_get_recent_changes
from openai_docs_scraper.mcp_server import get_stats as mcp_get_stats
from openai_docs_scraper.mcp_server import search_docs as mcp_search_docs
from openai_docs_scraper.services import run_refresh
from openai_docs_scraper.services.config import get_settings
from openai_docs_scraper.services.state import collect_artifact_state


def _write_cached_page(raw_dir: Path, name: str, *, url: str, title: str, raw_html: str) -> None:
    payload = {
        "url": url,
        "title": title,
        "raw": raw_html,
        "body": None,
        "hash": name,
    }
    (raw_dir / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def _make_html(title: str, paragraphs: list[str]) -> str:
    filler = (
        " This fixture paragraph intentionally adds extra explanatory text so the "
        "ingestion pipeline treats it as a valid documentation page instead of a short stub."
    )
    body = "".join(f"<p>{paragraph}{filler}</p>" for paragraph in paragraphs)
    return f"<html><body><main><article><h1>{title}</h1>{body}</article></main></body></html>"


def main() -> None:
    with TemporaryDirectory(prefix="openai-docs-gate-") as tmpdir:
        print("gate: setup")
        root = Path(tmpdir)
        raw_dir = root / "raw"
        raw_dir.mkdir()
        db_path = root / "docs.sqlite3"
        export_root = root / "export"
        export_root.mkdir()
        (export_root / "index.md").write_text("# Local Index\n", encoding="utf-8")
        guide_dir = export_root / "guides"
        guide_dir.mkdir()
        (guide_dir / "function-calling.md").write_text("# Function Calling\n", encoding="utf-8")
        sitemap_path = root / "sitemap.xml"
        sitemap_path.write_text("<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'></urlset>", encoding="utf-8")

        _write_cached_page(
            raw_dir,
            "function-calling",
            url="https://platform.openai.com/docs/guides/function-calling",
            title="Function Calling",
            raw_html=_make_html(
                "Function Calling",
                [
                    "Function calling lets models decide when to call tools.",
                    "This page explains schemas, tool arguments, and the execution loop.",
                    "Use it when you want structured tool calls with validated arguments.",
                    "One more paragraph keeps the page long enough to pass the ingest threshold.",
                ],
            ),
        )

        os.environ["DB_PATH"] = str(db_path)
        os.environ["RAW_DIR"] = str(raw_dir)
        os.environ["MD_EXPORT_ROOT"] = str(export_root)
        os.environ["SITEMAP_PATH"] = str(sitemap_path)
        get_settings.cache_clear()
        run_refresh(
            db_path=db_path,
            raw_dir=raw_dir,
            sitemap_path=sitemap_path,
            fetch_latest_sitemap=False,
        )
        state = collect_artifact_state(get_settings())
        print(f"gate: direct state pages_total={state.pages_total}")
        assert state.active_snapshot_id is not None
        assert state.latest_run_status == "succeeded"

        print("gate: api health")
        health = anyio.run(health_check)
        assert health["db_exists"] is True

        print("gate: api search")
        search = anyio.run(
            api_search_post,
            SearchRequest(q="function calling", no_embed=True, k=3),
        )
        assert search.hits

        print("gate: api answer")
        answer = anyio.run(
            api_answer_post,
            AnswerRequest(q="How does function calling work?", no_embed=True, synthesis_mode="extractive"),
        )
        assert answer.citations

        print("gate: docs stats")
        docs_stats = anyio.run(api_docs_stats)
        assert docs_stats.pages_total == 1

        print("gate: docs changes")
        changes = anyio.run(api_get_changes, None, 10)
        assert changes.new_pages

        print("gate: api config")
        config = anyio.run(app_config)
        assert config["source_name"] == "openai_docs"

        print("gate: mcp stats")
        mcp_stats = json.loads(mcp_get_stats())
        assert mcp_stats["pages_total"] == 1

        print("gate: mcp changes")
        mcp_changes = json.loads(mcp_get_recent_changes(limit=10))
        assert mcp_changes["new_pages"]

        print("gate: mcp search")
        mcp_search = json.loads(mcp_search_docs(query="function calling", k=3, target="chunks", no_embed=True))
        assert mcp_search

        print("gate: mcp answer")
        mcp_answer = json.loads(
            mcp_answer_question(
                question="How does function calling work?",
                k=4,
                citations_limit=2,
                target="chunks",
                no_embed=True,
                synthesis_mode="extractive",
            )
        )
        assert mcp_answer["citations"]

        print("full_gate_a_smoke: ok")


if __name__ == "__main__":
    main()
