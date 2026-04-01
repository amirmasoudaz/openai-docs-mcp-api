"""History, diff, and run-level change reporting helpers."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path
from typing import Optional

from ..book_export import rel_md_path_from_url
from ..db import connect, init_db


@dataclass(frozen=True)
class PageRevisionRecord:
    url: str
    title: str | None
    section: str | None
    content_version: int
    content_hash: str | None
    observed_at: str
    plain_text: str | None
    source_hash: str | None


@dataclass(frozen=True)
class PageHistoryResult:
    url: str
    title: str | None
    section: str | None
    current_content_version: int | None
    page_state: str | None
    changed_at: str | None
    deleted_at: str | None
    revisions: list[PageRevisionRecord]


@dataclass(frozen=True)
class PageDiffResult:
    url: str
    from_version: int
    to_version: int
    from_observed_at: str | None
    to_observed_at: str | None
    diff: str


@dataclass(frozen=True)
class ChangeEntry:
    url: str
    title: str | None
    section: str | None
    content_version: int | None
    observed_at: str | None
    md_relpath: str


@dataclass(frozen=True)
class RunChangeReport:
    run_id: str
    run_status: str | None
    run_stage: str | None
    started_at: str | None
    finished_at: str | None
    new_pages: list[ChangeEntry]
    changed_pages: list[ChangeEntry]
    deleted_pages: list[ChangeEntry]


def _get_page_row(con, url: str):
    row = con.execute(
        """
        SELECT id, url, title, section, content_version, page_state, changed_at, deleted_at, plain_text
        FROM pages
        WHERE url = ?;
        """,
        (url,),
    ).fetchone()
    if row is None:
        raise ValueError(f"page not found: {url}")
    return row


def get_page_history(db_path: str | Path, *, url: str) -> PageHistoryResult:
    db_path = Path(db_path)
    con = connect(db_path)
    init_db(con)
    page = _get_page_row(con, url)
    revisions = con.execute(
        """
        SELECT p.url, p.section, r.title, r.content_version, r.content_hash, r.observed_at, r.plain_text, r.source_hash
        FROM page_revisions r
        JOIN pages p ON p.id = r.page_id
        WHERE p.url = ?
        ORDER BY r.content_version;
        """,
        (url,),
    ).fetchall()
    con.close()
    return PageHistoryResult(
        url=str(page["url"]),
        title=page["title"],
        section=page["section"],
        current_content_version=int(page["content_version"]) if page["content_version"] is not None else None,
        page_state=page["page_state"],
        changed_at=page["changed_at"],
        deleted_at=page["deleted_at"],
        revisions=[
            PageRevisionRecord(
                url=str(r["url"]),
                title=r["title"],
                section=r["section"],
                content_version=int(r["content_version"]),
                content_hash=r["content_hash"],
                observed_at=r["observed_at"],
                plain_text=r["plain_text"],
                source_hash=r["source_hash"],
            )
            for r in revisions
        ],
    )


def _get_revision_text(history: PageHistoryResult, version: int) -> tuple[str, str | None]:
    for revision in history.revisions:
        if revision.content_version == version:
            return (revision.plain_text or "", revision.observed_at)
    raise ValueError(f"version {version} not found for page: {history.url}")


def diff_page_versions(
    db_path: str | Path,
    *,
    url: str,
    from_version: int | None = None,
    to_version: int | None = None,
) -> PageDiffResult:
    history = get_page_history(db_path, url=url)
    versions = [r.content_version for r in history.revisions]
    if not versions:
        raise ValueError(f"no revisions available for page: {url}")
    if to_version is None:
        to_version = versions[-1]
    if from_version is None:
        earlier = [v for v in versions if v < to_version]
        if not earlier:
            raise ValueError(f"page has no earlier revision to diff against: {url}")
        from_version = earlier[-1]

    from_text, from_observed_at = _get_revision_text(history, from_version)
    to_text, to_observed_at = _get_revision_text(history, to_version)
    diff_lines = unified_diff(
        from_text.splitlines(),
        to_text.splitlines(),
        fromfile=f"{url}@v{from_version}",
        tofile=f"{url}@v{to_version}",
        lineterm="",
    )
    return PageDiffResult(
        url=url,
        from_version=from_version,
        to_version=to_version,
        from_observed_at=from_observed_at,
        to_observed_at=to_observed_at,
        diff="\n".join(diff_lines),
    )


def _resolve_run_id(con, run_id: str | None) -> str:
    if run_id:
        return run_id
    source_row = con.execute(
        """
        SELECT latest_run_id
        FROM sources
        ORDER BY updated_at DESC
        LIMIT 1;
        """
    ).fetchone()
    if source_row and source_row["latest_run_id"]:
        return str(source_row["latest_run_id"])
    derived = con.execute(
        """
        SELECT MAX(run_id) AS run_id
        FROM (
          SELECT last_seen_run_id AS run_id FROM pages WHERE last_seen_run_id IS NOT NULL
          UNION ALL
          SELECT observed_at AS run_id FROM page_revisions WHERE observed_at IS NOT NULL
          UNION ALL
          SELECT deleted_at AS run_id FROM pages WHERE deleted_at IS NOT NULL
        );
        """
    ).fetchone()
    if not derived or not derived["run_id"]:
        raise ValueError("no runs found")
    return str(derived["run_id"])


def get_run_changes(
    db_path: str | Path,
    *,
    run_id: str | None = None,
    limit: int = 50,
) -> RunChangeReport:
    db_path = Path(db_path)
    con = connect(db_path)
    init_db(con)
    resolved_run_id = _resolve_run_id(con, run_id)
    run_row = con.execute(
        """
        SELECT id, status, stage, started_at, finished_at
        FROM runs
        WHERE id = ?;
        """,
        (resolved_run_id,),
    ).fetchone()
    revision_rows = con.execute(
        """
        SELECT p.url, p.section, r.title, r.content_version, r.observed_at
        FROM page_revisions r
        JOIN pages p ON p.id = r.page_id
        WHERE r.observed_at = ?
        ORDER BY r.content_version, p.url
        LIMIT ?;
        """,
        (resolved_run_id, limit),
    ).fetchall()
    deleted_rows = con.execute(
        """
        SELECT url, title, section, content_version, deleted_at
        FROM pages
        WHERE deleted_at = ?
        ORDER BY url
        LIMIT ?;
        """,
        (resolved_run_id, limit),
    ).fetchall()
    con.close()

    new_pages: list[ChangeEntry] = []
    changed_pages: list[ChangeEntry] = []
    for row in revision_rows:
        entry = ChangeEntry(
            url=str(row["url"]),
            title=row["title"],
            section=row["section"],
            content_version=int(row["content_version"]) if row["content_version"] is not None else None,
            observed_at=row["observed_at"],
            md_relpath=rel_md_path_from_url(str(row["url"])).as_posix(),
        )
        if int(row["content_version"]) == 1:
            new_pages.append(entry)
        else:
            changed_pages.append(entry)
    deleted_pages = [
        ChangeEntry(
            url=str(row["url"]),
            title=row["title"],
            section=row["section"],
            content_version=int(row["content_version"]) if row["content_version"] is not None else None,
            observed_at=row["deleted_at"],
            md_relpath=rel_md_path_from_url(str(row["url"])).as_posix(),
        )
        for row in deleted_rows
    ]
    return RunChangeReport(
        run_id=resolved_run_id,
        run_status=run_row["status"] if run_row else None,
        run_stage=run_row["stage"] if run_row else None,
        started_at=run_row["started_at"] if run_row else None,
        finished_at=run_row["finished_at"] if run_row else None,
        new_pages=new_pages,
        changed_pages=changed_pages,
        deleted_pages=deleted_pages,
    )
