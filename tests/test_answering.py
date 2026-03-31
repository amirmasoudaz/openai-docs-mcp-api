from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from openai_docs_scraper.api.main import app
from openai_docs_scraper.db import connect, init_db
from openai_docs_scraper.ingest_cached import ingest_cached_pages
from openai_docs_scraper.services.answering import answer_question


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


def test_answer_service_returns_citations_and_freshness(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    db_path = tmp_path / "docs.sqlite3"
    page_url = "https://platform.openai.com/docs/guides/function-calling"

    _write_cached_page(
        raw_dir,
        "function-calling",
        url=page_url,
        title="Function Calling",
        raw_html=_make_html(
            "Function Calling",
            [
                "Function calling lets models decide when to call tools and return structured arguments.",
                "This page explains schemas, tool arguments, and the execution loop.",
                "Developers can validate arguments and run tool calls before sending final responses.",
                "One more paragraph keeps the page long enough to pass the ingest threshold.",
            ],
        ),
    )

    con = connect(db_path)
    init_db(con)
    ingest_cached_pages(con=con, raw_dir=raw_dir, force=False)
    con.close()

    result = answer_question(
        db_path=db_path,
        question="How does function calling work?",
        k=4,
        citations_limit=2,
        no_embed=True,
        synthesis_mode="extractive",
    )

    assert result.answer
    assert result.citations
    assert result.citations[0].url == page_url
    assert result.citations[0].md_relpath == "guides/function-calling.md"
    assert result.freshness.newest_last_seen_at is not None
    assert result.freshness.stale_summary_count == 0
    assert result.synthesis_mode == "extractive"


def test_answer_service_warns_when_cited_summary_and_embedding_are_stale(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    db_path = tmp_path / "docs.sqlite3"
    page_url = "https://platform.openai.com/docs/guides/structured-outputs"

    _write_cached_page(
        raw_dir,
        "structured-outputs",
        url=page_url,
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
        SET summary_for_hash = 'old-hash',
            embedding_for_hash = 'older-summary-hash'
        WHERE url = ?;
        """,
        (page_url,),
    )
    con.commit()
    con.close()

    result = answer_question(
        db_path=db_path,
        question="What are structured outputs for?",
        k=4,
        citations_limit=2,
        no_embed=True,
        synthesis_mode="extractive",
    )

    assert result.freshness.stale_summary_count == 1
    assert result.freshness.stale_page_embedding_count == 1
    assert any("stale page summaries" in warning for warning in result.warnings)
    assert any("stale page embeddings" in warning for warning in result.warnings)


def test_answer_api_returns_grounded_response_shape(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    db_path = tmp_path / "docs.sqlite3"
    page_url = "https://platform.openai.com/docs/guides/embeddings"

    _write_cached_page(
        raw_dir,
        "embeddings",
        url=page_url,
        title="Embeddings",
        raw_html=_make_html(
            "Embeddings",
            [
                "Embeddings turn text into vectors for semantic search and retrieval.",
                "This page explains cosine similarity, vector storage, and nearest-neighbor lookup.",
                "Use embeddings when you need semantic matching instead of exact keyword matching.",
                "One more paragraph keeps the page long enough to pass the ingest threshold.",
            ],
        ),
    )

    con = connect(db_path)
    init_db(con)
    ingest_cached_pages(con=con, raw_dir=raw_dir, force=False)
    con.close()

    client = TestClient(app)
    response = client.post(
        "/search/answer",
        json={
            "q": "What are embeddings used for?",
            "db_path": str(db_path),
            "k": 4,
            "citations_limit": 2,
            "no_embed": True,
            "synthesis_mode": "extractive",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["question"] == "What are embeddings used for?"
    assert payload["answer"]
    assert payload["citations"]
    assert payload["citations"][0]["url"] == page_url
    assert payload["citations"][0]["md_relpath"] == "guides/embeddings.md"
    assert "freshness" in payload
    assert payload["synthesis_mode"] == "extractive"
