from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def connect(db_path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def init_db(con: sqlite3.Connection) -> None:
    # WAL can be faster, but in some sandboxed environments it intermittently fails
    # with "unable to open database file" due to shared-memory/WAL sidecar files.
    # Use DELETE journaling for reliability.
    con.execute("PRAGMA journal_mode=DELETE;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA foreign_keys=ON;")

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pages (
          id INTEGER PRIMARY KEY,
          url TEXT NOT NULL UNIQUE,
          section TEXT,
          title TEXT,
          raw_html TEXT,
          raw_body_text TEXT,
          main_html TEXT,
          raw_markdown TEXT,
          plain_text TEXT,
          content_hash TEXT,
          scraped_at TEXT,
          ingested_at TEXT,
          source_path TEXT,
          source_hash TEXT,
          http_status INTEGER,
          error TEXT,
          summary TEXT,
          summary_model TEXT,
          summary_updated_at TEXT,
          summary_for_hash TEXT,
          embedding BLOB,
          embedding_model TEXT,
          embedding_updated_at TEXT,
          embedding_for_hash TEXT,
          content_version INTEGER,
          changed_at TEXT,
          page_state TEXT,
          last_seen_at TEXT,
          last_seen_run_id TEXT,
          deleted_at TEXT,
          deletion_reason TEXT,
          export_for_hash TEXT,
          export_updated_at TEXT
        );
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
          id INTEGER PRIMARY KEY,
          page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
          chunk_index INTEGER NOT NULL,
          heading_path TEXT,
          chunk_markdown TEXT,
          chunk_text TEXT,
          chunk_hash TEXT,
          embedding BLOB,
          embedding_model TEXT,
          embedding_updated_at TEXT,
          embedding_for_hash TEXT,
          UNIQUE(page_id, chunk_index)
        );
        """
    )

    con.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
        USING fts5(chunk_text, content='chunks', content_rowid='id');
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS page_revisions (
          id INTEGER PRIMARY KEY,
          page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
          content_version INTEGER NOT NULL,
          content_hash TEXT,
          title TEXT,
          plain_text TEXT,
          observed_at TEXT NOT NULL,
          source_hash TEXT,
          UNIQUE(page_id, content_version)
        );
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS sources (
          name TEXT PRIMARY KEY,
          adapter_name TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          latest_run_id TEXT,
          latest_successful_run_id TEXT,
          active_snapshot_id TEXT
        );
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY,
          source_name TEXT NOT NULL,
          trigger TEXT NOT NULL,
          status TEXT NOT NULL,
          stage TEXT,
          started_at TEXT NOT NULL,
          finished_at TEXT,
          error_summary TEXT,
          pages_seen INTEGER NOT NULL DEFAULT 0,
          pages_ingested INTEGER NOT NULL DEFAULT 0,
          pages_unchanged INTEGER NOT NULL DEFAULT 0,
          pages_new INTEGER NOT NULL DEFAULT 0,
          pages_changed INTEGER NOT NULL DEFAULT 0,
          pages_deleted INTEGER NOT NULL DEFAULT 0,
          pages_failed INTEGER NOT NULL DEFAULT 0,
          chunks_written INTEGER NOT NULL DEFAULT 0,
          summaries_invalidated INTEGER NOT NULL DEFAULT 0,
          page_embeddings_invalidated INTEGER NOT NULL DEFAULT 0,
          chunk_embeddings_invalidated INTEGER NOT NULL DEFAULT 0,
          exports_invalidated INTEGER NOT NULL DEFAULT 0
        );
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
          id TEXT PRIMARY KEY,
          source_name TEXT NOT NULL,
          run_id TEXT NOT NULL UNIQUE,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          published_at TEXT,
          db_path TEXT,
          export_root TEXT,
          sitemap_path TEXT,
          pages_total INTEGER NOT NULL DEFAULT 0,
          chunks_total INTEGER NOT NULL DEFAULT 0
        );
        """
    )

    con.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
          INSERT INTO chunks_fts(rowid, chunk_text) VALUES (new.id, new.chunk_text);
        END;
        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
          INSERT INTO chunks_fts(chunks_fts, rowid, chunk_text) VALUES ('delete', old.id, old.chunk_text);
        END;
        CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
          INSERT INTO chunks_fts(chunks_fts, rowid, chunk_text) VALUES ('delete', old.id, old.chunk_text);
          INSERT INTO chunks_fts(rowid, chunk_text) VALUES (new.id, new.chunk_text);
        END;
        """
    )

    _ensure_column(con, "pages", "raw_html", "TEXT")
    _ensure_column(con, "pages", "section", "TEXT")
    _ensure_column(con, "pages", "main_html", "TEXT")
    _ensure_column(con, "pages", "raw_body_text", "TEXT")
    _ensure_column(con, "pages", "ingested_at", "TEXT")
    _ensure_column(con, "pages", "source_path", "TEXT")
    _ensure_column(con, "pages", "source_hash", "TEXT")
    _ensure_column(con, "pages", "summary_for_hash", "TEXT")
    _ensure_column(con, "pages", "embedding_for_hash", "TEXT")
    _ensure_column(con, "pages", "content_version", "INTEGER")
    _ensure_column(con, "pages", "changed_at", "TEXT")
    _ensure_column(con, "pages", "page_state", "TEXT")
    _ensure_column(con, "pages", "last_seen_at", "TEXT")
    _ensure_column(con, "pages", "last_seen_run_id", "TEXT")
    _ensure_column(con, "pages", "deleted_at", "TEXT")
    _ensure_column(con, "pages", "deletion_reason", "TEXT")
    _ensure_column(con, "pages", "export_for_hash", "TEXT")
    _ensure_column(con, "pages", "export_updated_at", "TEXT")
    _ensure_column(con, "chunks", "embedding_for_hash", "TEXT")
    _ensure_column(con, "page_revisions", "plain_text", "TEXT")
    _ensure_column(con, "sources", "latest_run_id", "TEXT")
    _ensure_column(con, "sources", "latest_successful_run_id", "TEXT")
    _ensure_column(con, "sources", "active_snapshot_id", "TEXT")
    _ensure_column(con, "runs", "stage", "TEXT")
    _ensure_column(con, "runs", "finished_at", "TEXT")
    _ensure_column(con, "runs", "error_summary", "TEXT")
    _ensure_column(con, "runs", "pages_seen", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(con, "runs", "pages_ingested", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(con, "runs", "pages_unchanged", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(con, "runs", "pages_new", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(con, "runs", "pages_changed", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(con, "runs", "pages_deleted", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(con, "runs", "pages_failed", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(con, "runs", "chunks_written", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(con, "runs", "summaries_invalidated", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(con, "runs", "page_embeddings_invalidated", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(con, "runs", "chunk_embeddings_invalidated", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(con, "runs", "exports_invalidated", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(con, "snapshots", "db_path", "TEXT")
    _ensure_column(con, "snapshots", "export_root", "TEXT")
    _ensure_column(con, "snapshots", "sitemap_path", "TEXT")
    _ensure_column(con, "snapshots", "pages_total", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(con, "snapshots", "chunks_total", "INTEGER NOT NULL DEFAULT 0")

    con.execute("CREATE INDEX IF NOT EXISTS idx_pages_section ON pages(section);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_pages_deleted_at ON pages(deleted_at);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_pages_page_state ON pages(page_state);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_chunks_page_id ON chunks(page_id);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_runs_source_started_at ON runs(source_name, started_at DESC);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_source_published_at ON snapshots(source_name, published_at DESC);")
    con.commit()


def _ensure_column(con: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    cols = {row["name"] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
    if column in cols:
        return
    con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type};")


def ensure_source(
    con: sqlite3.Connection,
    *,
    source_name: str,
    adapter_name: str | None = None,
    observed_at: str,
) -> None:
    adapter_name = adapter_name or source_name
    con.execute(
        """
        INSERT INTO sources(name, adapter_name, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
          adapter_name = excluded.adapter_name,
          updated_at = excluded.updated_at;
        """,
        (source_name, adapter_name, observed_at, observed_at),
    )
    con.commit()


def create_run(
    con: sqlite3.Connection,
    *,
    run_id: str,
    source_name: str,
    trigger: str,
    status: str,
    stage: str | None,
    started_at: str,
) -> None:
    con.execute(
        """
        INSERT OR REPLACE INTO runs(id, source_name, trigger, status, stage, started_at)
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        (run_id, source_name, trigger, status, stage, started_at),
    )
    con.execute(
        """
        UPDATE sources
        SET latest_run_id = ?, updated_at = ?
        WHERE name = ?;
        """,
        (run_id, started_at, source_name),
    )
    con.commit()


def update_run(
    con: sqlite3.Connection,
    *,
    run_id: str,
    source_name: str,
    status: str | None = None,
    stage: str | None = None,
    finished_at: str | None = None,
    error_summary: str | None = None,
    stats: dict[str, int] | None = None,
) -> None:
    assignments: list[str] = []
    values: list[Any] = []
    if status is not None:
        assignments.append("status = ?")
        values.append(status)
    if stage is not None:
        assignments.append("stage = ?")
        values.append(stage)
    if finished_at is not None:
        assignments.append("finished_at = ?")
        values.append(finished_at)
    if error_summary is not None:
        assignments.append("error_summary = ?")
        values.append(error_summary)
    if stats:
        for key in (
            "pages_seen",
            "pages_ingested",
            "pages_unchanged",
            "pages_new",
            "pages_changed",
            "pages_deleted",
            "pages_failed",
            "chunks_written",
            "summaries_invalidated",
            "page_embeddings_invalidated",
            "chunk_embeddings_invalidated",
            "exports_invalidated",
        ):
            if key in stats:
                assignments.append(f"{key} = ?")
                values.append(int(stats[key]))
    if not assignments:
        return
    values.append(run_id)
    con.execute(f"UPDATE runs SET {', '.join(assignments)} WHERE id = ?;", values)
    if status == "succeeded":
        timestamp = finished_at or con.execute(
            "SELECT finished_at FROM runs WHERE id = ?;",
            (run_id,),
        ).fetchone()["finished_at"]
        con.execute(
            """
            UPDATE sources
            SET latest_run_id = ?,
                latest_successful_run_id = ?,
                updated_at = COALESCE(?, updated_at)
            WHERE name = ?;
            """,
            (run_id, run_id, timestamp, source_name),
        )
    elif status is not None:
        timestamp = finished_at or con.execute(
            "SELECT finished_at FROM runs WHERE id = ?;",
            (run_id,),
        ).fetchone()["finished_at"]
        con.execute(
            """
            UPDATE sources
            SET latest_run_id = ?,
                updated_at = COALESCE(?, updated_at)
            WHERE name = ?;
            """,
            (run_id, timestamp, source_name),
        )
    con.commit()


def publish_snapshot(
    con: sqlite3.Connection,
    *,
    snapshot_id: str,
    source_name: str,
    run_id: str,
    created_at: str,
    published_at: str,
    db_path: str,
    export_root: str | None,
    sitemap_path: str | None,
    pages_total: int,
    chunks_total: int,
) -> None:
    con.execute(
        """
        INSERT OR REPLACE INTO snapshots(
          id, source_name, run_id, status, created_at, published_at,
          db_path, export_root, sitemap_path, pages_total, chunks_total
        )
        VALUES (?, ?, ?, 'published', ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            snapshot_id,
            source_name,
            run_id,
            created_at,
            published_at,
            db_path,
            export_root,
            sitemap_path,
            pages_total,
            chunks_total,
        ),
    )
    con.execute(
        """
        UPDATE sources
        SET active_snapshot_id = ?,
            latest_run_id = ?,
            latest_successful_run_id = ?,
            updated_at = ?
        WHERE name = ?;
        """,
        (snapshot_id, run_id, run_id, published_at, source_name),
    )
    con.commit()


def upsert_page(
    con: sqlite3.Connection,
    *,
    url: str,
    section: str | None,
    title: str | None,
    raw_html: str | None,
    raw_body_text: str | None,
    main_html: str | None,
    plain_text: str | None,
    content_hash: str | None,
    scraped_at: str,
    ingested_at: str | None,
    source_path: str | None,
    source_hash: str | None,
    http_status: int | None,
    error: str | None,
    content_version: int | None,
    changed_at: str | None,
    page_state: str | None,
    last_seen_at: str | None,
    last_seen_run_id: str | None,
    deleted_at: str | None,
    deletion_reason: str | None,
) -> int:
    # NOTE: Avoid a single large UPSERT statement here.
    # In some sandboxed environments SQLite can fail with "unable to open database file"
    # when binding very large strings into an UPSERT with many columns.
    con.execute("INSERT OR IGNORE INTO pages(url) VALUES (?);", (url,))
    con.execute(
        """
        UPDATE pages
        SET
          section = ?,
          title = ?,
          raw_html = ?,
          raw_body_text = ?,
          main_html = ?,
          plain_text = ?,
          content_hash = ?,
          scraped_at = ?,
          ingested_at = ?,
          source_path = ?,
          source_hash = ?,
          http_status = ?,
          error = ?,
          content_version = ?,
          changed_at = ?,
          page_state = ?,
          last_seen_at = ?,
          last_seen_run_id = ?,
          deleted_at = ?,
          deletion_reason = ?
        WHERE url = ?;
        """,
        (
            section,
            title,
            raw_html,
            raw_body_text,
            main_html,
            plain_text,
            content_hash,
            scraped_at,
            ingested_at,
            source_path,
            source_hash,
            http_status,
            error,
            content_version,
            changed_at,
            page_state,
            last_seen_at,
            last_seen_run_id,
            deleted_at,
            deletion_reason,
            url,
        ),
    )
    row = con.execute("SELECT id FROM pages WHERE url = ?;", (url,)).fetchone()
    if row is None:
        raise RuntimeError("Failed to upsert page row.")
    con.commit()
    return int(row["id"])


def replace_chunks(
    con: sqlite3.Connection,
    *,
    page_id: int,
    chunks: list[dict[str, str | int | None]],
) -> None:
    con.execute("DELETE FROM chunks WHERE page_id = ?;", (page_id,))
    for chunk in chunks:
        con.execute(
            """
            INSERT INTO chunks(
              page_id, chunk_index, heading_path, chunk_markdown, chunk_text, chunk_hash
            )
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                page_id,
                int(chunk["chunk_index"]),
                chunk.get("heading_path"),
                chunk.get("chunk_markdown"),
                chunk.get("chunk_text"),
                chunk.get("chunk_hash"),
            ),
        )
    con.commit()


def insert_page_revision(
    con: sqlite3.Connection,
    *,
    page_id: int,
    content_version: int,
    content_hash: str | None,
    title: str | None,
    plain_text: str | None,
    observed_at: str,
    source_hash: str | None,
) -> None:
    con.execute(
        """
        INSERT OR IGNORE INTO page_revisions(
          page_id, content_version, content_hash, title, plain_text, observed_at, source_hash
        )
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        (page_id, content_version, content_hash, title, plain_text, observed_at, source_hash),
    )
    con.commit()


def mark_pages_exported(
    con: sqlite3.Connection,
    *,
    exported_at: str,
    page_hashes: list[tuple[str, str | None]],
) -> None:
    for url, content_hash in page_hashes:
        con.execute(
            """
            UPDATE pages
            SET export_for_hash = ?,
                export_updated_at = ?
            WHERE url = ?;
            """,
            (content_hash, exported_at, url),
        )
    con.commit()
