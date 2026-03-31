from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
import re

QUERY_PHRASE_ALIASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bresponse(?:s)? api\b", re.IGNORECASE), "responses api"),
    (re.compile(r"\bchat completion(?:s)? api\b", re.IGNORECASE), "chat completions api"),
    (re.compile(r"\bassistant(?:s)? api\b", re.IGNORECASE), "assistants api"),
)

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "could",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "of",
    "on",
    "or",
    "should",
    "tell",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "work",
    "works",
}


def normalize_query_text(text: str) -> str:
    normalized = text or ""
    for pattern, replacement in QUERY_PHRASE_ALIASES:
        normalized = pattern.sub(replacement, normalized)
    return normalized


@dataclass
class RankingCandidate:
    url: str
    title: str | None
    summary: str | None
    chunk_text: str
    source_path: str | None
    md_relpath: str
    lexical_raw: float | None = None
    vector_raw: float | None = None
    score: float = 0.0
    score_details: dict[str, float] = field(default_factory=dict)


def _tokens(text: str, *, drop_stopwords: bool = True) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    if not drop_stopwords:
        return tokens
    filtered = [token for token in tokens if token not in STOPWORDS]
    return filtered or tokens


def _term_ratio(query_tokens: list[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    haystack = set(_tokens(text))
    if not haystack:
        return 0.0
    matched = sum(1 for token in query_tokens if token in haystack)
    return matched / len(query_tokens)


def _normalize(values: list[float | None], *, invert: bool = False) -> list[float]:
    usable = [value for value in values if value is not None]
    if not usable:
        return [0.0] * len(values)

    adjusted = [(-value if invert else value) for value in usable]
    lo = min(adjusted)
    hi = max(adjusted)

    out: list[float] = []
    for value in values:
        if value is None:
            out.append(0.0)
            continue
        current = -value if invert else value
        if hi == lo:
            out.append(1.0)
            continue
        out.append((current - lo) / (hi - lo))
    return out


def _phrase(text: str) -> str:
    tokens = _tokens(text)
    return " ".join(tokens)


def _phrase_hit(query_phrase: str, text: str) -> float:
    if not query_phrase:
        return 0.0
    haystack = " ".join(_tokens(text, drop_stopwords=False))
    return 1.0 if query_phrase in haystack else 0.0


def _is_explanatory_query(query: str) -> bool:
    lowered = (query or "").lower()
    return any(
        marker in lowered
        for marker in ("how ", "what ", "why ", "when ", "overview", "explain", "works", "work?")
    )


def rank_candidates(
    query: str,
    candidates: list[RankingCandidate],
    *,
    limit: int,
) -> list[RankingCandidate]:
    normalized_query = normalize_query_text(query)
    query_tokens = _tokens(normalized_query)
    query_phrase = _phrase(normalized_query)
    explanatory_query = _is_explanatory_query(normalized_query)
    lexical_norms = _normalize([candidate.lexical_raw for candidate in candidates], invert=True)
    vector_norms = _normalize([candidate.vector_raw for candidate in candidates], invert=False)

    ranked: list[RankingCandidate] = []
    for candidate, lexical_norm, vector_norm in zip(candidates, lexical_norms, vector_norms, strict=True):
        body_ratio = _term_ratio(query_tokens, " ".join(filter(None, [candidate.chunk_text, candidate.summary])))
        title_ratio = _term_ratio(query_tokens, candidate.title or "")
        path_ratio = _term_ratio(query_tokens, candidate.md_relpath)
        body_phrase = _phrase_hit(query_phrase, " ".join(filter(None, [candidate.chunk_text, candidate.summary])))
        title_phrase = _phrase_hit(query_phrase, candidate.title or "")
        path_phrase = _phrase_hit(query_phrase, candidate.md_relpath)
        section = PurePosixPath(candidate.md_relpath).parts[0] if candidate.md_relpath else ""
        guide_boost = 1.0 if explanatory_query and section == "guides" else 0.0
        preview_text = " ".join(filter(None, [candidate.title, candidate.summary, candidate.chunk_text[:200]])).lower()
        deprecated_penalty = 1.0 if "deprecated" in preview_text else 0.0
        lexical_match_quality = max(body_ratio, title_ratio, path_ratio)
        effective_lexical = lexical_norm * lexical_match_quality

        path_depth = len(PurePosixPath(candidate.md_relpath).parts)
        depth_prior = 1.0 / max(path_depth, 1)

        if candidate.lexical_raw is not None and candidate.vector_raw is not None:
            total = (
                0.58 * vector_norm
                + 0.20 * effective_lexical
                + 0.12 * body_ratio
                + 0.07 * title_ratio
                + 0.02 * path_ratio
                + 0.07 * title_phrase
                + 0.03 * path_phrase
                + 0.02 * body_phrase
                + 0.08 * guide_boost
                - 0.12 * deprecated_penalty
                + 0.01 * depth_prior
            )
        elif candidate.vector_raw is not None:
            total = (
                0.72 * vector_norm
                + 0.18 * body_ratio
                + 0.07 * title_ratio
                + 0.02 * path_ratio
                + 0.07 * title_phrase
                + 0.03 * path_phrase
                + 0.02 * body_phrase
                + 0.08 * guide_boost
                - 0.12 * deprecated_penalty
                + 0.01 * depth_prior
            )
        else:
            total = (
                0.35 * effective_lexical
                + 0.20 * body_ratio
                + 0.20 * title_ratio
                + 0.10 * path_ratio
                + 0.10 * title_phrase
                + 0.04 * path_phrase
                + 0.005 * body_phrase
                + 0.08 * guide_boost
                - 0.12 * deprecated_penalty
                + 0.005 * depth_prior
            )

        candidate.score = round(total, 6)
        candidate.score_details = {
            "lexical_raw": round(candidate.lexical_raw, 6) if candidate.lexical_raw is not None else 0.0,
            "lexical_norm": round(lexical_norm, 6),
            "effective_lexical": round(effective_lexical, 6),
            "vector_raw": round(candidate.vector_raw, 6) if candidate.vector_raw is not None else 0.0,
            "vector_norm": round(vector_norm, 6),
            "body_term_ratio": round(body_ratio, 6),
            "title_term_ratio": round(title_ratio, 6),
            "path_term_ratio": round(path_ratio, 6),
            "body_phrase_hit": round(body_phrase, 6),
            "title_phrase_hit": round(title_phrase, 6),
            "path_phrase_hit": round(path_phrase, 6),
            "guide_boost": round(guide_boost, 6),
            "deprecated_penalty": round(deprecated_penalty, 6),
            "path_depth_prior": round(depth_prior, 6),
            "total": round(total, 6),
        }
        ranked.append(candidate)

    ranked.sort(key=lambda candidate: candidate.score, reverse=True)
    return ranked[:limit]
