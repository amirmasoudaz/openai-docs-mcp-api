from __future__ import annotations

from openai_docs_scraper.ranking import RankingCandidate, rank_candidates


def test_rank_candidates_combines_vector_lexical_and_structural_signals() -> None:
    candidates = [
        RankingCandidate(
            url="https://platform.openai.com/docs/guides/function-calling",
            title="Function Calling",
            summary="Guide to tool calls and structured arguments.",
            chunk_text="Define tools with JSON schema arguments and execution loops.",
            source_path=None,
            md_relpath="guides/function-calling.md",
            lexical_raw=-3.0,
            vector_raw=0.88,
        ),
        RankingCandidate(
            url="https://platform.openai.com/docs/guides/structured-outputs",
            title="Structured Outputs",
            summary="Guide to strict JSON schemas.",
            chunk_text="Use structured outputs for schema-constrained JSON responses.",
            source_path=None,
            md_relpath="guides/structured-outputs.md",
            lexical_raw=-1.0,
            vector_raw=0.40,
        ),
    ]

    ranked = rank_candidates("function calling tool schema", candidates, limit=2)

    assert ranked[0].url == "https://platform.openai.com/docs/guides/function-calling"
    assert ranked[0].score > ranked[1].score
    assert ranked[0].score_details["vector_norm"] >= 0.0
    assert ranked[0].score_details["lexical_norm"] >= 0.0
    assert ranked[0].score_details["title_term_ratio"] > 0.0
