from __future__ import annotations

import sqlite3
from pathlib import Path


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
          embedding_for_hash TEXT
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
    _ensure_column(con, "chunks", "embedding_for_hash", "TEXT")

    con.execute("CREATE INDEX IF NOT EXISTS idx_pages_section ON pages(section);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_chunks_page_id ON chunks(page_id);")
    con.commit()


def _ensure_column(con: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    cols = {row["name"] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
    if column in cols:
        return
    con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type};")


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
          error = ?
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
