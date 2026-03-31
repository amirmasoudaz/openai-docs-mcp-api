from __future__ import annotations

import json
from pathlib import Path

from openai_docs_scraper.db import connect, init_db
from openai_docs_scraper.ingest_cached import ingest_cached_pages
from openai_docs_scraper.services.search import query


def test_fts_query_handles_punctuation_in_model_names(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    db_path = tmp_path / "docs.sqlite3"

    payload = {
        "url": "https://platform.openai.com/docs/models/gpt-4.1",
        "title": "GPT-4.1",
        "raw": (
            "<html><body><main><article><h1>GPT-4.1</h1>"
            "<p>GPT-4.1 is a capable model with long context and strong coding quality.</p>"
            "<p>Use it for instruction following, larger prompts, and harder coding tasks.</p>"
            "<p>This extra paragraph keeps the fixture above the minimum ingest threshold for valid pages.</p>"
            "<p>Another paragraph mentions GPT-4.1 again so the model identifier appears in the indexed content.</p>"
            "</article></main></body></html>"
        ),
        "body": None,
        "hash": "gpt-fixture",
    }
    (raw_dir / "gpt.json").write_text(json.dumps(payload), encoding="utf-8")

    con = connect(db_path)
    init_db(con)
    ingest_cached_pages(con=con, raw_dir=raw_dir, force=True)
    con.close()

    hits = query(
        db_path=db_path,
        q="gpt-4.1 long context",
        k=3,
        no_embed=True,
        target="chunks",
    )

    assert hits
    assert hits[0].url == "https://platform.openai.com/docs/models/gpt-4.1"
