from __future__ import annotations

from openai_docs_scraper.extract import infer_section
from openai_docs_scraper.sources import get_source, list_sources


def test_openai_source_adapter_maps_urls_and_paths() -> None:
    source = get_source("openai_docs")

    assert source.normalize_url("HTTPS://platform.openai.com/docs/guides/structured-outputs/") == (
        "https://platform.openai.com/docs/guides/structured-outputs"
    )
    assert source.infer_section("https://platform.openai.com/docs/guides/structured-outputs") == "guides"
    assert source.export_relpath("https://platform.openai.com/docs/models/gpt-4.1").as_posix() == "models/gpt-4.1.md"


def test_extract_infer_section_uses_source_adapter() -> None:
    assert infer_section("https://platform.openai.com/docs/guides/function-calling") == "guides"
    assert infer_section("https://platform.openai.com/docs") is None


def test_source_registry_lists_openai_adapter() -> None:
    assert "openai_docs" in list_sources()
