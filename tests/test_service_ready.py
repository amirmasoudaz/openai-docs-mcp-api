from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from openai_docs_scraper.api.main import app
from openai_docs_scraper.db import connect, init_db
from openai_docs_scraper.ingest_cached import ingest_cached_pages
from openai_docs_scraper.mcp_server import get_stats as mcp_get_stats
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


def test_health_and_config_surface_source_and_artifact_metadata(tmp_path: Path, monkeypatch) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    db_path = tmp_path / "docs.sqlite3"
    export_root = tmp_path / "export"
    export_root.mkdir()
    (export_root / "index.md").write_text("# Index\n", encoding="utf-8")
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
                "The fixture is intentionally verbose enough to pass ingest validation.",
                "One more paragraph keeps the page long enough to avoid blocked-or-too-short classification.",
            ],
        ),
    )

    con = connect(db_path)
    init_db(con)
    ingest_cached_pages(con=con, raw_dir=raw_dir, force=False)
    con.close()

    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("RAW_DIR", str(raw_dir))
    monkeypatch.setenv("MD_EXPORT_ROOT", str(export_root))
    monkeypatch.setenv("SITEMAP_PATH", str(sitemap_path))
    get_settings.cache_clear()

    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    health_payload = health.json()
    assert health_payload["source_name"] == "openai_docs"
    assert "openai_docs" in health_payload["available_sources"]
    assert health_payload["db_exists"] is True
    assert health_payload["raw_dir_exists"] is True
    assert health_payload["md_export_root_exists"] is True
    assert health_payload["index_md_exists"] is True

    config = client.get("/config")
    assert config.status_code == 200
    config_payload = config.json()
    assert config_payload["source_name"] == "openai_docs"
    assert "answer_model" in config_payload


def test_docs_stats_and_mcp_stats_include_snapshot_metadata(tmp_path: Path, monkeypatch) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    db_path = tmp_path / "docs.sqlite3"
    export_root = tmp_path / "export"
    export_root.mkdir()
    (export_root / "index.md").write_text("# Index\n", encoding="utf-8")
    sitemap_path = tmp_path / "sitemap.xml"
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

    con = connect(db_path)
    init_db(con)
    ingest_cached_pages(con=con, raw_dir=raw_dir, force=False)
    con.execute(
        """
        UPDATE pages
        SET summary_for_hash = 'stale-summary-hash',
            embedding_for_hash = 'stale-embedding-hash'
        """
    )
    con.commit()
    con.close()

    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("RAW_DIR", str(raw_dir))
    monkeypatch.setenv("MD_EXPORT_ROOT", str(export_root))
    monkeypatch.setenv("SITEMAP_PATH", str(sitemap_path))
    get_settings.cache_clear()

    client = TestClient(app)
    response = client.get("/docs/stats")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source_name"] == "openai_docs"
    assert payload["raw_cache_files"] == 1
    assert payload["stale_summaries"] == 1
    assert payload["stale_page_embeddings"] == 1
    assert payload["latest_run_id"] is not None

    mcp_payload = json.loads(mcp_get_stats())
    assert mcp_payload["source_name"] == "openai_docs"
    assert mcp_payload["stale_summaries"] == 1
    assert mcp_payload["stale_page_embeddings"] == 1
