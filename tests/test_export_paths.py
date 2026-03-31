from __future__ import annotations

from openai_docs_scraper.book_export import normalize_doc_url, rel_md_path_from_url


def test_rel_md_path_from_url_maps_docs_paths_stably() -> None:
    assert (
        rel_md_path_from_url("https://platform.openai.com/docs/guides/structured-outputs").as_posix()
        == "guides/structured-outputs.md"
    )
    assert rel_md_path_from_url("https://platform.openai.com/docs").as_posix() == "index.md"
    assert rel_md_path_from_url("https://platform.openai.com/docs/models/gpt-4.1").as_posix() == "models/gpt-4.1.md"


def test_normalize_doc_url_collapses_trailing_slashes() -> None:
    normalized = normalize_doc_url("HTTPS://platform.openai.com/docs/guides/structured-outputs/")
    assert normalized == "https://platform.openai.com/docs/guides/structured-outputs"
