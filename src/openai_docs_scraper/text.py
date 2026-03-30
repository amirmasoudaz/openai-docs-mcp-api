from __future__ import annotations

import hashlib
import re


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def collapse_single_newlines_outside_fences(text: str) -> str:
    """
    Turn single newlines into spaces outside ``` fenced blocks (common Markdown).
    Keeps paragraph breaks (\\n\\n) and code fences intact. Improves prose
    where BeautifulSoup used \\n between inline siblings (e.g. link on its own line).
    """
    if not text or "```" not in text:
        return re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    parts = text.split("```")
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"(?<!\n)\n(?!\n)", " ", parts[i])
    return "```".join(parts)


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text_paragraphs(
    text: str,
    *,
    max_chars: int = 2500,
    overlap_chars: int = 200,
) -> list[str]:
    text = normalize_whitespace(text)
    if not text:
        return []

    if overlap_chars >= max_chars:
        overlap_chars = max(0, max_chars // 5)

    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0

    def flush() -> None:
        nonlocal buf, buf_len
        if not buf:
            return
        chunk = "\n\n".join(buf).strip()
        if chunk:
            chunks.append(chunk)
        buf = []
        buf_len = 0

    for para in paras:
        if len(para) > max_chars:
            flush()
            start = 0
            while start < len(para):
                end = min(len(para), start + max_chars)
                chunks.append(para[start:end].strip())
                if end >= len(para):
                    break
                start = max(0, end - overlap_chars)
            continue

        if buf_len + len(para) + (2 if buf else 0) > max_chars:
            flush()
        buf.append(para)
        buf_len += len(para) + (2 if buf_len else 0)

    flush()
    return chunks
