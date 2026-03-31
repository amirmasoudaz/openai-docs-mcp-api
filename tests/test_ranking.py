from __future__ import annotations

from openai_docs_scraper.ranking import RankingCandidate, normalize_query_text, rank_candidates
from openai_docs_scraper.search import fts_match_query


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


def test_rank_candidates_downweights_question_stopwords_and_prefers_exact_title_match() -> None:
    candidates = [
        RankingCandidate(
            url="https://platform.openai.com/docs/guides/reasoning-best-practices",
            title="Reasoning Best Practices",
            summary="Examples of models that use function calling in AI workflows at work.",
            chunk_text="The model uses function calling to pull information from your calendar or email at work.",
            source_path=None,
            md_relpath="guides/reasoning-best-practices.md",
            lexical_raw=-1.0,
            vector_raw=None,
        ),
        RankingCandidate(
            url="https://platform.openai.com/docs/guides/function-calling",
            title="Function Calling",
            summary="Guide to tool calling and structured arguments.",
            chunk_text="Function calling gives models access to tools and explains the request, tool call, and tool output loop.",
            source_path=None,
            md_relpath="guides/function-calling.md",
            lexical_raw=-2.0,
            vector_raw=None,
        ),
    ]

    ranked = rank_candidates("How does function calling work?", candidates, limit=2)

    assert ranked[0].url == "https://platform.openai.com/docs/guides/function-calling"
    assert ranked[0].score_details["title_phrase_hit"] == 1.0


def test_fts_match_query_omits_question_stopwords() -> None:
    assert fts_match_query("How does function calling work?") == '"function" OR "calling"'


def test_query_normalization_canonicalizes_responses_api() -> None:
    assert normalize_query_text("How does Response API work?") == "How does responses api work?"
    assert fts_match_query("How does Response API work?") == '"responses" OR "api"'


def test_rank_candidates_prefers_guide_over_deprecated_page_for_explanatory_queries() -> None:
    candidates = [
        RankingCandidate(
            url="https://platform.openai.com/docs/assistants/tools/function-calling",
            title="Assistants Function Calling",
            summary="Deprecated Assistants API function calling workflow.",
            chunk_text="Deprecated. The Assistants API supports function calling and tool outputs.",
            source_path=None,
            md_relpath="assistants/tools/function-calling.md",
            lexical_raw=-1.0,
            vector_raw=None,
        ),
        RankingCandidate(
            url="https://platform.openai.com/docs/guides/function-calling",
            title="Function Calling",
            summary="Guide to the tool calling loop.",
            chunk_text="Function calling explains the request, tool call, execution, and tool output flow.",
            source_path=None,
            md_relpath="guides/function-calling.md",
            lexical_raw=-1.2,
            vector_raw=None,
        ),
    ]

    ranked = rank_candidates("How does function calling work?", candidates, limit=2)

    assert ranked[0].url == "https://platform.openai.com/docs/guides/function-calling"
    assert ranked[0].score_details["guide_boost"] == 1.0
    assert ranked[1].score_details["deprecated_penalty"] == 1.0
