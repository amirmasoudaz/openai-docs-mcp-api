"""Summarization service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..db import connect, init_db
from ..env import require_openai_api_key
from ..openai_ops import OpenAIModels, summarize_very_short


@dataclass(frozen=True)
class SummarizeResult:
    """Result of a summarization operation."""

    total_candidates: int
    updated: int


def summarize_pages(
    db_path: str | Path,
    *,
    model: Optional[str] = None,
    limit: int = 50,
    force: bool = False,
    section: Optional[str] = None,
) -> SummarizeResult:
    """
    Generate summaries for pages in the database.

    Args:
        db_path: Path to the SQLite database.
        model: OpenAI model to use for summarization.
        limit: Maximum number of pages to summarize.
        force: Force re-summarization even if already done.
        section: Only summarize pages in this section.

    Returns:
        SummarizeResult with statistics.
    """
    require_openai_api_key()

    if model is None:
        model = OpenAIModels().summary_model

    db_path = Path(db_path)
    con = connect(db_path)
    init_db(con)

    where = "deleted_at IS NULL AND plain_text IS NOT NULL AND (error IS NULL OR error = '')"
    params: list[object] = []

    if section:
        where += " AND section = ?"
        params.append(section)

    if not force:
        where += " AND (summary IS NULL OR summary_for_hash IS NULL OR summary_for_hash != content_hash)"

    rows = con.execute(
        f"""
        SELECT id, url, title, raw_markdown, plain_text, content_hash
        FROM pages
        WHERE {where}
        LIMIT ?;
        """,
        (*params, limit),
    ).fetchall()

    total_candidates = len(rows)
    updated = 0

    for r in rows:
        text = (r["raw_markdown"] or r["plain_text"] or "").strip()
        summary = summarize_very_short(text=text, model=model)
        con.execute(
            """
            UPDATE pages
            SET summary = ?, summary_model = ?, summary_updated_at = datetime('now'),
                summary_for_hash = ?
            WHERE id = ?;
            """,
            (summary, model, r["content_hash"], r["id"]),
        )
        con.commit()
        updated += 1

    con.close()

    return SummarizeResult(total_candidates=total_candidates, updated=updated)
