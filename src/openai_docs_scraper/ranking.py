from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
import re


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


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


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


def rank_candidates(
    query: str,
    candidates: list[RankingCandidate],
    *,
    limit: int,
) -> list[RankingCandidate]:
    query_tokens = _tokens(query)
    lexical_norms = _normalize([candidate.lexical_raw for candidate in candidates], invert=True)
    vector_norms = _normalize([candidate.vector_raw for candidate in candidates], invert=False)

    ranked: list[RankingCandidate] = []
    for candidate, lexical_norm, vector_norm in zip(candidates, lexical_norms, vector_norms, strict=True):
        body_ratio = _term_ratio(query_tokens, " ".join(filter(None, [candidate.chunk_text, candidate.summary])))
        title_ratio = _term_ratio(query_tokens, candidate.title or "")
        path_ratio = _term_ratio(query_tokens, candidate.md_relpath)
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
                + 0.01 * depth_prior
            )
        elif candidate.vector_raw is not None:
            total = (
                0.72 * vector_norm
                + 0.18 * body_ratio
                + 0.07 * title_ratio
                + 0.02 * path_ratio
                + 0.01 * depth_prior
            )
        else:
            total = (
                0.72 * effective_lexical
                + 0.18 * body_ratio
                + 0.07 * title_ratio
                + 0.02 * path_ratio
                + 0.01 * depth_prior
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
            "path_depth_prior": round(depth_prior, 6),
            "total": round(total, 6),
        }
        ranked.append(candidate)

    ranked.sort(key=lambda candidate: candidate.score, reverse=True)
    return ranked[:limit]
