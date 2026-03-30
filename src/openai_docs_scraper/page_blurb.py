"""Short descriptions for doc pages (navigation index)."""

from __future__ import annotations

import re
from pathlib import Path


SECTION_RE = re.compile(r"^\*\*Section:\*\*\s*`([^`]*)`", re.MULTILINE)
SOURCE_RE = re.compile(r"^\*\*Source:\*\*\s*(\S+)", re.MULTILINE)


def parse_page_metadata_and_body(md: str) -> tuple[str | None, str | None, str | None, str]:
    """
    From a split/rebuilt page: (# title, section, source_url, body_after_metadata).
    """
    lines = md.splitlines()
    title: str | None = None
    i = 0
    if i < len(lines) and lines[i].startswith("# "):
        title = lines[i][2:].strip()
        i += 1

    while i < len(lines) and not lines[i].strip():
        i += 1

    meta_start = i
    while i < len(lines) and lines[i].strip().startswith("**"):
        i += 1
    header_blob = "\n".join(lines[meta_start:i])
    sm = SECTION_RE.search(header_blob)
    section = sm.group(1).strip() if sm else None
    um = SOURCE_RE.search(header_blob)
    source = um.group(1).strip() if um else None

    while i < len(lines) and not lines[i].strip():
        i += 1

    body = "\n".join(lines[i:])
    return title, section, source, body


def heuristic_blurb(body: str, *, max_chars: int = 240) -> str:
    """
    First substantive lines of prose (no API). Skips UI cruft like 'Copy page'.
    """
    body = (body or "").strip()
    if not body:
        return ""

    skip_exact = {"copy page", "next steps"}
    collected: list[str] = []

    for line in body.splitlines():
        raw = line.strip()
        if not raw:
            if collected:
                break
            continue
        low = raw.lower()
        if low in skip_exact:
            continue
        if raw.startswith("#"):
            if collected:
                break
            continue
        if raw.startswith("```"):
            if collected:
                break
            continue
        if raw.startswith("!["):
            continue
        if len(raw) <= 2 and raw.isdigit():
            continue

        collected.append(raw)
        flat = " ".join(collected)
        if len(flat) >= max_chars:
            break

    out = " ".join(collected).strip()
    if len(out) > max_chars:
        cut = out[: max_chars - 1]
        out = cut.rsplit(" ", 1)[0] + "…"
    return out


def openai_blurb(body: str, *, model: str | None = None, max_input_chars: int = 20_000) -> str:
    """One–two sentence summary via OpenAI (requires OPENAI_API_KEY)."""
    from .env import require_openai_api_key
    from .openai_ops import OpenAIModels, summarize_very_short

    require_openai_api_key()
    m = model or OpenAIModels().summary_model
    text = (body or "").strip()[:max_input_chars]
    if not text:
        return ""
    return summarize_very_short(text=text, model=m).strip()


def section_from_rel_path(rel: Path) -> str:
    """Infer grouping key from path (e.g. guides/foo.md -> guides)."""
    parts = rel.parts
    if len(parts) >= 2:
        return parts[0]
    stem = rel.stem
    return stem if stem else "other"


def _escape_md_inline(text: str) -> str:
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def collect_nav_index_rows(
    out_root: Path,
    *,
    use_openai: bool = False,
    openai_model: str | None = None,
    max_blurb_chars: int = 240,
) -> list[tuple[Path, str, str, str]]:
    """
    Scan ``out_root`` for ``*.md`` (except index.md).

    Each row: (relative path, title, section_for_toc, blurb).
    """
    rows: list[tuple[Path, str, str, str]] = []
    for path in sorted(out_root.rglob("*.md")):
        if path.name == "index.md":
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        title, section, _src, body = parse_page_metadata_and_body(raw)
        sec = (section or "").strip() or section_from_rel_path(path.relative_to(out_root))
        display_title = (title or path.stem).strip()
        if use_openai:
            blurb = openai_blurb(body, model=openai_model)
        else:
            blurb = heuristic_blurb(body, max_chars=max_blurb_chars)
        rows.append((path.relative_to(out_root), display_title, sec, blurb))
    return rows


def format_navigation_index(
    rows: list[tuple[Path, str, str, str]],
    *,
    intro_extra: str | None = None,
) -> str:
    """Markdown text for index.md grouped by section."""
    from collections import defaultdict

    by_sec: dict[str, list[tuple[Path, str, str]]] = defaultdict(list)
    for rel, title, sec, blurb in rows:
        by_sec[sec].append((rel, title, blurb))

    lines = [
        "# OpenAI docs — navigation index",
        "",
        "Each entry links to the page and includes a short preview of the content.",
    ]
    if intro_extra:
        lines.append("")
        lines.append(intro_extra)
    lines.extend(
        [
            "",
            "## Pages by section",
            "",
        ]
    )

    for sec in sorted(by_sec.keys(), key=str.lower):
        lines.append(f"### {sec}")
        lines.append("")
        for rel, title, blurb in sorted(by_sec[sec], key=lambda x: x[0].as_posix()):
            link = rel.as_posix()
            t = _escape_md_inline(title)
            desc = blurb.strip() if blurb else "_(no preview)_"
            lines.append(f"- **[{link}]({link})** — *{t}* — {desc}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_navigation_index(
    out_root: Path,
    *,
    use_openai: bool = False,
    openai_model: str | None = None,
    max_blurb_chars: int = 240,
    intro_extra: str | None = None,
) -> None:
    rows = collect_nav_index_rows(
        out_root,
        use_openai=use_openai,
        openai_model=openai_model,
        max_blurb_chars=max_blurb_chars,
    )
    text = format_navigation_index(rows, intro_extra=intro_extra)
    (out_root / "index.md").write_text(text, encoding="utf-8")


def write_navigation_index_from_rows(
    out_root: Path,
    rows: list[tuple[Path, str, str, str]],
    *,
    intro_extra: str | None = None,
) -> None:
    """Write index.md from rows ``(rel_path, title, section, blurb)`` (no disk scan)."""
    text = format_navigation_index(rows, intro_extra=intro_extra)
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "index.md").write_text(text, encoding="utf-8")
