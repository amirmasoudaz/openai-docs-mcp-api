from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from openai_docs_scraper.api.main import app
from openai_docs_scraper.db import connect, init_db
from openai_docs_scraper.ingest_cached import ingest_cached_pages
from openai_docs_scraper.mcp_server import get_page_diff as mcp_get_page_diff
from openai_docs_scraper.mcp_server import get_page_history as mcp_get_page_history
from openai_docs_scraper.mcp_server import get_recent_changes as mcp_get_recent_changes
from openai_docs_scraper.services.config import get_settings


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


def test_api_and_mcp_expose_page_history_diff_and_run_changes(tmp_path: Path, monkeypatch) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    db_path = tmp_path / "docs.sqlite3"
    export_root = tmp_path / "export"
    export_root.mkdir()
    (export_root / "index.md").write_text("# Index\n", encoding="utf-8")
    sitemap_path = tmp_path / "sitemap.xml"
    sitemap_path.write_text("<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'></urlset>", encoding="utf-8")

    changed_url = "https://platform.openai.com/docs/guides/function-calling"
    deleted_url = "https://platform.openai.com/docs/guides/rate-limits"
    new_url = "https://platform.openai.com/docs/guides/structured-outputs"

    _write_cached_page(
        raw_dir,
        "function-calling",
        url=changed_url,
        title="Function Calling",
        raw_html=_make_html(
            "Function Calling",
            [
                "Function calling lets models call tools.",
                "This first revision explains the basic execution loop.",
                "The fixture is intentionally verbose enough to pass ingest validation.",
                "One more paragraph keeps the page long enough to avoid blocked-or-too-short classification.",
            ],
        ),
    )
    _write_cached_page(
        raw_dir,
        "rate-limits",
        url=deleted_url,
        title="Rate Limits",
        raw_html=_make_html(
            "Rate Limits",
            [
                "Rate limits require clients to retry with backoff.",
                "This first revision explains quotas and smoothing.",
                "The fixture is intentionally verbose enough to pass ingest validation.",
                "One more paragraph keeps the page long enough to avoid blocked-or-too-short classification.",
            ],
        ),
    )

    con = connect(db_path)
    init_db(con)
    ingest_cached_pages(con=con, raw_dir=raw_dir, run_id="run-1", force=False)

    _write_cached_page(
        raw_dir,
        "function-calling",
        url=changed_url,
        title="Function Calling",
        raw_html=_make_html(
            "Function Calling",
            [
                "Function calling lets models call tools and validate arguments.",
                "This updated revision explains execution loops, retries, and tool results.",
                "The fixture changed enough to produce a meaningful diff.",
                "One more paragraph keeps the page long enough to avoid blocked-or-too-short classification.",
            ],
        ),
    )
    (raw_dir / "rate-limits.json").unlink()
    _write_cached_page(
        raw_dir,
        "structured-outputs",
        url=new_url,
        title="Structured Outputs",
        raw_html=_make_html(
            "Structured Outputs",
            [
                "Structured outputs enforce schemas for model responses.",
                "This new page explains deterministic JSON and validation.",
                "The fixture is intentionally verbose enough to pass ingest validation.",
                "One more paragraph keeps the page long enough to avoid blocked-or-too-short classification.",
            ],
        ),
    )
    ingest_cached_pages(con=con, raw_dir=raw_dir, run_id="run-2", force=False)
    con.close()

    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("RAW_DIR", str(raw_dir))
    monkeypatch.setenv("MD_EXPORT_ROOT", str(export_root))
    monkeypatch.setenv("SITEMAP_PATH", str(sitemap_path))
    get_settings.cache_clear()

    client = TestClient(app)

    history = client.get("/docs/page/history", params={"url": changed_url})
    assert history.status_code == 200
    history_payload = history.json()
    assert history_payload["current_content_version"] == 2
    assert history_payload["page_state"] == "changed"
    assert [r["content_version"] for r in history_payload["revisions"]] == [1, 2]

    diff = client.get(
        "/docs/page/diff",
        params={"url": changed_url, "from_version": 1, "to_version": 2},
    )
    assert diff.status_code == 200
    diff_payload = diff.json()
    assert diff_payload["from_version"] == 1
    assert diff_payload["to_version"] == 2
    assert "-Function calling lets models call tools." in diff_payload["diff"]
    assert "+Function calling lets models call tools and validate arguments." in diff_payload["diff"]

    changes = client.get("/docs/changes", params={"run_id": "run-2"})
    assert changes.status_code == 200
    changes_payload = changes.json()
    assert [entry["url"] for entry in changes_payload["new_pages"]] == [new_url]
    assert [entry["url"] for entry in changes_payload["changed_pages"]] == [changed_url]
    assert [entry["url"] for entry in changes_payload["deleted_pages"]] == [deleted_url]

    mcp_history = json.loads(mcp_get_page_history(changed_url))
    assert mcp_history["current_content_version"] == 2

    mcp_diff = json.loads(mcp_get_page_diff(changed_url, from_version=1, to_version=2))
    assert "+Function calling lets models call tools and validate arguments." in mcp_diff["diff"]

    mcp_changes = json.loads(mcp_get_recent_changes(run_id="run-2"))
    assert [entry["url"] for entry in mcp_changes["new_pages"]] == [new_url]
    assert [entry["url"] for entry in mcp_changes["changed_pages"]] == [changed_url]
    assert [entry["url"] for entry in mcp_changes["deleted_pages"]] == [deleted_url]
