from __future__ import annotations

from openai_docs_scraper.text import chunk_text_paragraphs, collapse_single_newlines_outside_fences


def test_collapse_single_newlines_preserves_code_fences() -> None:
    text = "Line one\nline two\n\n```python\nprint('x')\nprint('y')\n```\n\nTail\nline"
    collapsed = collapse_single_newlines_outside_fences(text)

    assert "Line one line two" in collapsed
    assert "Tail line" in collapsed
    assert "print('x')\nprint('y')" in collapsed


def test_chunk_text_paragraphs_preserves_paragraphs_and_overlap() -> None:
    text = "\n\n".join(
        [
            "Paragraph one has enough text to stay intact.",
            "Paragraph two is also short and should fit with others.",
            "A" * 80,
        ]
    )

    chunks = chunk_text_paragraphs(text, max_chars=90, overlap_chars=20)

    assert len(chunks) >= 2
    assert "Paragraph one has enough text to stay intact." in chunks[0]
    assert any("Paragraph two is also short" in chunk for chunk in chunks)
    long_chunks = [chunk for chunk in chunks if "A" * 20 in chunk]
    assert len(long_chunks) >= 1


def test_chunk_text_paragraphs_splits_long_paragraph_with_overlap() -> None:
    text = "B" * 120

    chunks = chunk_text_paragraphs(text, max_chars=50, overlap_chars=10)

    assert len(chunks) == 3
    assert chunks[0] == "B" * 50
    assert chunks[1].startswith("B" * 10)
    assert chunks[2] == "B" * 40
