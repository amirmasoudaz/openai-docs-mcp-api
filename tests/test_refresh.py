from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from openai_docs_scraper.db import connect
from openai_docs_scraper.services.config import get_settings
from openai_docs_scraper.services.refresh import RefreshLockedError, run_refresh
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


def test_run_refresh_publishes_snapshot_and_updates_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    db_path = tmp_path / "docs.sqlite3"
    sitemap_path = tmp_path / "sitemap.xml"
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

    result = run_refresh(
        db_path=db_path,
        raw_dir=raw_dir,
        sitemap_path=sitemap_path,
        fetch_latest_sitemap=False,
    )

    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("RAW_DIR", str(raw_dir))
    monkeypatch.setenv("SITEMAP_PATH", str(sitemap_path))
    get_settings.cache_clear()

    state = collect_artifact_state(get_settings())
    assert result.status == "succeeded"
    assert state.latest_run_id == result.run_id
    assert state.latest_run_status == "succeeded"
    assert state.latest_successful_run_id == result.run_id
    assert state.active_snapshot_id == result.snapshot_id
    assert state.active_snapshot_pages_total == 1
    assert state.active_snapshot_chunks_total >= 1


def test_failed_refresh_keeps_previous_snapshot_published(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    db_path = tmp_path / "docs.sqlite3"
    sitemap_path = tmp_path / "sitemap.xml"
    sitemap_path.write_text("<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'></urlset>", encoding="utf-8")

    _write_cached_page(
        raw_dir,
        "responses",
        url="https://platform.openai.com/docs/guides/migrate-to-responses",
        title="Responses API",
        raw_html=_make_html(
            "Responses API",
            [
                "The Responses API is the current OpenAI API for tool use and structured outputs.",
                "This guide explains migration, input formatting, and multi-turn behavior.",
                "The fixture is intentionally long enough to pass ingestion validation.",
                "One more paragraph keeps the extracted body above the too-short threshold.",
            ],
        ),
    )

    first = run_refresh(
        db_path=db_path,
        raw_dir=raw_dir,
        sitemap_path=sitemap_path,
        fetch_latest_sitemap=False,
    )
    sitemap_path.unlink()

    with pytest.raises(FileNotFoundError):
        run_refresh(
            db_path=db_path,
            raw_dir=raw_dir,
            sitemap_path=sitemap_path,
            fetch_latest_sitemap=False,
        )

    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("RAW_DIR", str(raw_dir))
    monkeypatch.setenv("SITEMAP_PATH", str(sitemap_path))
    get_settings.cache_clear()

    state = collect_artifact_state(get_settings())
    assert state.latest_run_status == "failed"
    assert state.latest_successful_run_id == first.run_id
    assert state.active_snapshot_id == first.snapshot_id
    assert state.pages_total == 1

    con = connect(db_path)
    row = con.execute("SELECT title FROM pages WHERE deleted_at IS NULL").fetchone()
    con.close()
    assert row["title"] == "Responses API"


def test_refresh_refuses_active_lock_and_recovers_stale_lock(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    db_path = tmp_path / "docs.sqlite3"
    sitemap_path = tmp_path / "sitemap.xml"
    lock_path = tmp_path / "locks" / "openai_docs.lock"
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

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text('{"run_id":"other-run"}', encoding="utf-8")
    with pytest.raises(RefreshLockedError):
        run_refresh(
            db_path=db_path,
            raw_dir=raw_dir,
            sitemap_path=sitemap_path,
            fetch_latest_sitemap=False,
            lock_path=lock_path,
            lock_timeout_s=3600,
        )

    old_mtime = 1_700_000_000
    os.utime(lock_path, (old_mtime, old_mtime))
    result = run_refresh(
        db_path=db_path,
        raw_dir=raw_dir,
        sitemap_path=sitemap_path,
        fetch_latest_sitemap=False,
        lock_path=lock_path,
        lock_timeout_s=1,
    )
    assert result.status == "succeeded"
    assert lock_path.exists() is False


def test_refresh_writes_jsonl_run_logs(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    db_path = tmp_path / "docs.sqlite3"
    sitemap_path = tmp_path / "sitemap.xml"
    log_path = tmp_path / "logs" / "refresh.jsonl"
    sitemap_path.write_text("<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'></urlset>", encoding="utf-8")
    _write_cached_page(
        raw_dir,
        "structured-outputs",
        url="https://platform.openai.com/docs/guides/structured-outputs",
        title="Structured Outputs",
        raw_html=_make_html(
            "Structured Outputs",
            [
                "Structured outputs force responses to match a supplied schema.",
                "This page explains schema validation and strict output parsing.",
                "Use it when you need deterministic JSON and safer downstream parsing.",
                "One more paragraph keeps the page long enough to pass the ingest threshold.",
            ],
        ),
    )

    result = run_refresh(
        db_path=db_path,
        raw_dir=raw_dir,
        sitemap_path=sitemap_path,
        fetch_latest_sitemap=False,
        trigger="scheduled",
        log_path=log_path,
    )

    lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    events = [line["event"] for line in lines]
    assert events[0] == "run_started"
    assert "stage" in events
    assert events[-1] == "run_succeeded"
    assert lines[-1]["run_id"] == result.run_id
    assert lines[-1]["status"] == "succeeded"
