from __future__ import annotations

import json
from pathlib import Path

from openai_docs_scraper.db import connect, init_db, replace_chunks, upsert_page
from openai_docs_scraper.embeddings import pack_f32
from openai_docs_scraper.ingest_cached import ingest_cached_pages
from openai_docs_scraper.services.search import query


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


def test_ingest_skips_unchanged_pages(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    db_path = tmp_path / "docs.sqlite3"

    _write_cached_page(
        raw_dir,
        "structured",
        url="https://platform.openai.com/docs/guides/structured-outputs",
        title="Structured Outputs",
        raw_html=_make_html(
            "Structured Outputs",
            [
                "Use structured outputs to force JSON that matches a supplied schema.",
                "Validate tool responses and final answers with strict parsing rules.",
                "This paragraph adds enough content to avoid the blocked or too short heuristic.",
                "Another paragraph keeps the extracted text comfortably above the minimum threshold.",
            ],
        ),
    )

    con = connect(db_path)
    init_db(con)

    first = ingest_cached_pages(con=con, raw_dir=raw_dir, force=False)
    second = ingest_cached_pages(con=con, raw_dir=raw_dir, force=False)

    version_row = con.execute(
        "SELECT content_version FROM pages WHERE url = ?;",
        ("https://platform.openai.com/docs/guides/structured-outputs",),
    ).fetchone()
    revision_row = con.execute("SELECT COUNT(*) AS count FROM page_revisions").fetchone()
    row = con.execute("SELECT COUNT(*) AS count FROM pages").fetchone()
    chunk_row = con.execute("SELECT COUNT(*) AS count FROM chunks").fetchone()
    con.close()

    assert first["pages_seen"] == 1
    assert first["pages_ingested"] == 1
    assert second["pages_seen"] == 1
    assert second["pages_ingested"] == 0
    assert second["pages_unchanged"] == 1
    assert int(row["count"]) == 1
    assert int(chunk_row["count"]) >= 1
    assert int(version_row["content_version"]) == 1
    assert int(revision_row["count"]) == 1


def test_ingest_marks_short_pages_as_blocked(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    db_path = tmp_path / "docs.sqlite3"

    _write_cached_page(
        raw_dir,
        "short",
        url="https://platform.openai.com/docs/guides/short-page",
        title="Short Page",
        raw_html="<html><body><main><article><h1>Short Page</h1><p>Too short.</p></article></main></body></html>",
    )

    con = connect(db_path)
    init_db(con)
    stats = ingest_cached_pages(con=con, raw_dir=raw_dir, force=False)

    page = con.execute("SELECT error FROM pages").fetchone()
    chunk_row = con.execute("SELECT COUNT(*) AS count FROM chunks").fetchone()
    con.close()

    assert stats["pages_ingested"] == 1
    assert page["error"] == "blocked_or_too_short"
    assert int(chunk_row["count"]) == 0


def test_chunks_fts_triggers_follow_insert_update_and_delete(tmp_path: Path) -> None:
    db_path = tmp_path / "docs.sqlite3"
    con = connect(db_path)
    init_db(con)

    page_id = upsert_page(
        con,
        url="https://platform.openai.com/docs/guides/function-calling",
        section="guides",
        title="Function Calling",
        raw_html=None,
        raw_body_text=None,
        main_html=None,
        plain_text="Function calling lets models return structured tool calls.",
        content_hash="hash-1",
        scraped_at="2026-03-30T00:00:00+00:00",
        ingested_at="2026-03-30T00:00:00+00:00",
        source_path="fixture.json",
        source_hash="source-hash",
        http_status=None,
        error=None,
        content_version=1,
        changed_at="2026-03-30T00:00:00+00:00",
        last_seen_at="2026-03-30T00:00:00+00:00",
        last_seen_run_id="run-1",
        deleted_at=None,
        deletion_reason=None,
    )

    replace_chunks(
        con,
        page_id=page_id,
        chunks=[
            {
                "chunk_index": 0,
                "heading_path": None,
                "chunk_markdown": None,
                "chunk_text": "Function calling lets models request tools.",
                "chunk_hash": "chunk-1",
            }
        ],
    )
    inserted = con.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'tools';"
    ).fetchall()
    assert len(inserted) == 1

    replace_chunks(
        con,
        page_id=page_id,
        chunks=[
            {
                "chunk_index": 0,
                "heading_path": None,
                "chunk_markdown": None,
                "chunk_text": "Structured outputs can enforce JSON schemas.",
                "chunk_hash": "chunk-2",
            }
        ],
    )
    updated_old = con.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'tools';"
    ).fetchall()
    updated_new = con.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'schemas';"
    ).fetchall()
    assert len(updated_old) == 0
    assert len(updated_new) == 1

    con.execute("DELETE FROM chunks WHERE page_id = ?;", (page_id,))
    con.commit()
    deleted = con.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'schemas';"
    ).fetchall()
    con.close()

    assert len(deleted) == 0


def test_ingest_changed_page_invalidates_stale_artifacts_and_bumps_version(tmp_path: Path) -> None:
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
                "This page explains cosine similarity, vector storage, and search pipelines.",
                "The content is long enough to pass the ingest quality guard.",
                "Another paragraph keeps the fixture above the minimum threshold for ingestion.",
            ],
        ),
    )

    con = connect(db_path)
    init_db(con)
    first = ingest_cached_pages(con=con, raw_dir=raw_dir, force=False)
    assert first["pages_new"] == 1

    page_row = con.execute(
        "SELECT id, content_hash FROM pages WHERE url = ?;",
        (page_url,),
    ).fetchone()
    con.execute(
        """
        UPDATE pages
        SET summary = 'Old summary',
            summary_for_hash = ?,
            embedding = ?,
            embedding_for_hash = ?
        WHERE id = ?;
        """,
        (
            page_row["content_hash"],
            pack_f32([1.0, 0.0]),
            page_row["content_hash"],
            page_row["id"],
        ),
    )
    con.execute(
        """
        UPDATE chunks
        SET embedding = ?, embedding_for_hash = chunk_hash
        WHERE page_id = ?;
        """,
        (pack_f32([1.0, 0.0]), page_row["id"]),
    )
    con.commit()

    _write_cached_page(
        raw_dir,
        "embeddings",
        url=page_url,
        title="Embeddings",
        raw_html=_make_html(
            "Embeddings",
            [
                "Embeddings turn text into vectors for semantic search, retrieval, and reranking.",
                "This updated page explains cosine similarity, ANN indices, and vector-aware filtering.",
                "The content changed enough to trigger a new content version and downstream invalidation.",
                "Another paragraph keeps the fixture comfortably above the minimum threshold for ingestion.",
            ],
        ),
    )

    second = ingest_cached_pages(con=con, raw_dir=raw_dir, force=False)

    updated_page = con.execute(
        "SELECT content_version, content_hash, summary_for_hash, embedding_for_hash FROM pages WHERE url = ?;",
        (page_url,),
    ).fetchone()
    revision_row = con.execute(
        "SELECT COUNT(*) AS count FROM page_revisions WHERE page_id = ?;",
        (page_row["id"],),
    ).fetchone()
    con.close()

    assert second["pages_changed"] == 1
    assert second["summaries_invalidated"] == 1
    assert second["page_embeddings_invalidated"] == 1
    assert second["chunk_embeddings_invalidated"] >= 1
    assert int(updated_page["content_version"]) == 2
    assert updated_page["summary_for_hash"] != updated_page["content_hash"]
    assert updated_page["embedding_for_hash"] != updated_page["content_hash"]
    assert int(revision_row["count"]) == 2


def test_full_ingest_marks_missing_pages_deleted_and_removes_chunks(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    db_path = tmp_path / "docs.sqlite3"
    kept_url = "https://platform.openai.com/docs/guides/function-calling"
    removed_url = "https://platform.openai.com/docs/guides/rate-limits"

    _write_cached_page(
        raw_dir,
        "function-calling",
        url=kept_url,
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
    _write_cached_page(
        raw_dir,
        "rate-limits",
        url=removed_url,
        title="Rate Limits",
        raw_html=_make_html(
            "Rate Limits",
            [
                "Rate limits require clients to retry with backoff and jitter.",
                "This page explains quotas, smoothing, and capacity pressure handling.",
                "The fixture is intentionally verbose enough to pass ingest validation.",
                "One more paragraph keeps the page long enough to avoid blocked-or-too-short classification.",
            ],
        ),
    )

    con = connect(db_path)
    init_db(con)
    first = ingest_cached_pages(con=con, raw_dir=raw_dir, force=False)
    assert first["pages_new"] == 2

    (raw_dir / "rate-limits.json").unlink()
    second = ingest_cached_pages(con=con, raw_dir=raw_dir, force=False)

    deleted_page = con.execute(
        "SELECT deleted_at FROM pages WHERE url = ?;",
        (removed_url,),
    ).fetchone()
    kept_page = con.execute(
        "SELECT deleted_at FROM pages WHERE url = ?;",
        (kept_url,),
    ).fetchone()
    removed_chunks = con.execute(
        """
        SELECT COUNT(*) AS count
        FROM chunks c
        JOIN pages p ON p.id = c.page_id
        WHERE p.url = ?;
        """,
        (removed_url,),
    ).fetchone()
    con.close()

    hits = query(db_path=db_path, q="rate limits backoff", k=5, no_embed=True)

    assert second["pages_deleted"] == 1
    assert deleted_page["deleted_at"] is not None
    assert kept_page["deleted_at"] is None
    assert int(removed_chunks["count"]) == 0
    assert all(hit.url != removed_url for hit in hits)


def test_incremental_ingest_keeps_missing_pages_active(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    db_path = tmp_path / "docs.sqlite3"
    kept_url = "https://platform.openai.com/docs/guides/function-calling"
    removed_url = "https://platform.openai.com/docs/guides/rate-limits"

    _write_cached_page(
        raw_dir,
        "function-calling",
        url=kept_url,
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
    _write_cached_page(
        raw_dir,
        "rate-limits",
        url=removed_url,
        title="Rate Limits",
        raw_html=_make_html(
            "Rate Limits",
            [
                "Rate limits require clients to retry with backoff and jitter.",
                "This page explains quotas, smoothing, and capacity pressure handling.",
                "The fixture is intentionally verbose enough to pass ingest validation.",
                "One more paragraph keeps the page long enough to avoid blocked-or-too-short classification.",
            ],
        ),
    )

    con = connect(db_path)
    init_db(con)
    first = ingest_cached_pages(con=con, raw_dir=raw_dir, force=False)
    assert first["pages_new"] == 2

    (raw_dir / "rate-limits.json").unlink()
    second = ingest_cached_pages(
        con=con,
        raw_dir=raw_dir,
        force=False,
        mark_missing_deleted=False,
    )

    removed_page = con.execute(
        "SELECT deleted_at FROM pages WHERE url = ?;",
        (removed_url,),
    ).fetchone()
    con.close()

    hits = query(db_path=db_path, q="rate limits backoff", k=5, no_embed=True)

    assert second["pages_deleted"] == 0
    assert removed_page["deleted_at"] is None
    assert any(hit.url == removed_url for hit in hits)
