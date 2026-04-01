# llm-provider-docs-ledger

Agent-ready local retrieval system for LLM provider API docs.

This project captures provider documentation into deterministic local snapshots, normalizes pages into canonical Markdown, stores them in SQLite, indexes them with FTS5, optionally adds summaries and embeddings, and serves the corpus through CLI, HTTP API, and MCP tools for coding agents.

Today the repository ships one concrete source adapter, `openai_docs`, so the active corpus is OpenAI Platform documentation. The system is intentionally structured so other providers can be added behind the same ingestion, retrieval, and export pipeline.

It is intentionally more than a scraper:

- **Acquisition:** sitemap discovery plus browser-backed page capture into a raw JSON cache.
- **Normalization:** HTML extraction, markdown conversion, chunking, and canonical path mapping.
- **Storage and indexing:** SQLite tables for pages and chunks with trigger-synced FTS5 indexes.
- **Semantic processing:** optional page summaries and embeddings for vector search.
- **Serving:** CLI, FastAPI endpoints, markdown file export, and MCP tools.
- **Agent workflows:** exact file reads, navigation index access, and local-grounded retrieval for assistants.

**Full operations guide** (pipelines, API/MCP, Docker, updating data, GitHub publishing): [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md).

## Why this exists

Browsing live docs is fine for humans. It is weaker for local workflows that need deterministic retrieval, snapshot-based grounding, file-level export, or agent-compatible access paths.

This repository is built for those cases:

- local documentation search without forcing vector infrastructure everywhere
- reproducible snapshots for experiments, tooling, and evaluation
- canonical Markdown exports that agents and humans can read directly
- MCP-native doc access inside editor and assistant workflows

## System shape

```text
sitemap -> raw page cache -> extraction + chunking -> SQLite + FTS5
                                      -> summaries + embeddings (optional)
                                      -> split Markdown export
                                      -> CLI / API / MCP
```

## What is strong about the design

- **Dual retrieval modes:** cheap lexical retrieval with FTS5, plus optional vector search when semantic routing helps.
- **Page and chunk views:** page summaries help routing; chunk bodies preserve retrieval precision.
- **Canonical Markdown tree:** URLs map to stable markdown paths, which makes exact file retrieval and export practical.
- **Safe local file serving:** exported docs and cached source files are read under configured roots only.
- **Multiple interfaces:** the same corpus is usable through scripts, FastAPI, Docker, and MCP.

## Current limits

- **Single adapter today:** the core pipeline now runs through a source adapter boundary, but only the OpenAI docs adapter is implemented.
- **Local-first today:** the repo is service-ready in shape, not yet a deployed multi-user service with background jobs, auth, or shared tenancy.
- **Scraping is brittle by nature:** HTML structure, rate limiting, or auth changes upstream can break acquisition.

## High-value next steps

- A second concrete source adapter so the same pipeline can support SDK docs, product docs, and internal documentation sites.
- Snapshot orchestration and background job execution for scrape, ingest, summarize, embed, and export stages.
- A service deployment layer around the current local-first core, with shared storage and job state.
- Broader eval coverage using larger, more realistic query sets and source corpora.

## Source Adapters

The core retrieval/export pipeline now resolves source-specific behavior through adapters in `src/openai_docs_scraper/sources/`.

- adapters define sitemap defaults, URL normalization, section inference, and canonical export-path mapping
- the current implementation ships one adapter: `openai_docs`
- core helpers like section inference and markdown export mapping call the adapter boundary instead of hard-coding OpenAI URL rules inline

To add another source later, implement the adapter contract and register it in `openai_docs_scraper.sources`.

## Service-Ready Prep

Phase 6 hardens the repo for later service evolution without turning it into a hosted system yet.

- `/health`, `/config`, `/docs/stats`, and MCP `get_stats` now expose source, snapshot, stale-artifact, and path metadata
- `scripts/full_gate_a_smoke.py` exercises API, retrieval, grounded answers, docs stats, and MCP flows in one local command
- architecture and eval templates live in `docs/ARCHITECTURE.md` and `docs/EVAL_REPORT_TEMPLATE.md`

## Installation

```bash
pip install -e .
```

For development:
```bash
pip install -e ".[cli]"  # Includes optional CLI support
```

## API Server

Start the FastAPI server:

```bash
uvicorn openai_docs_scraper.api.main:app --reload --port 8000
```

With Docker Compose, the app listens on **port 8000** (see `docker-compose.yml`).

### Using the API (guidelines)

- **OpenAPI UI:** open [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger) or `/redoc` for schemas and “Try it out”.
- **POST bodies:** send `Content-Type: application/json`. Request models live in `src/openai_docs_scraper/api/schemas.py`.
- **Paths (`db_path`, `raw_dir`, `sitemap_path`, `out_path`):** optional on most routes. If omitted, values come from **environment / `.env`** (`DB_PATH`, `RAW_DIR`, `SITEMAP_PATH`, etc.). In Docker, set those to `/data/...` and you can call endpoints with **`{}`** or minimal JSON.
- **Source selection:** the current adapter is `openai_docs`; `/health`, `/config`, and `/docs/stats` expose the active source and snapshot metadata.
- **Import path:** the Python package name remains `openai_docs_scraper` for now even though the repository is named `llm-provider-docs-ledger`.
- **OpenAI:** `POST /process/summarize`, `POST /process/embed`, and **vector** search (`/search/query` with `no_embed: false`) need **`OPENAI_API_KEY`**. FTS-only search (`no_embed: true`) does not.

### API endpoints (full list)

**App root**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness plus source, path, snapshot, and stale-artifact state |
| `GET` | `/config` | Non-secret defaults: source, sitemap, paths, and default models |

**`/project`**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/project/init` | Create / initialize SQLite (`InitProjectRequest`) |
| `POST` | `/project/sitemap/fetch` | Download sitemap XML (`FetchSitemapRequest`) |
| `POST` | `/project/sitemap/list` | Parse local sitemap into URL entries (`ListSitemapRequest`) |

**`/scrape`**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/scrape/run` | Browser scrape into cache (`ScrapeRequest`; long-running) |

**`/ingest`**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ingest/cached` | Read `raw_dir` JSON → SQLite + chunks (`IngestRequest`, supports full-refresh vs incremental mode) |

**`/process`**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/process/summarize` | OpenAI summaries for pages (`SummarizeRequest`) |
| `POST` | `/process/embed` | Embeddings for `target` `pages` or `chunks` (`EmbedRequest`) |

**`/search`**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/search/query` | Query params: `q`, `k`, `target` (`chunks` \| `pages`), `fts`, `no_embed`, `group_pages`, `embedding_model`, optional `db_path` |
| `POST` | `/search/query` | JSON `SearchRequest`: same fields as body |
| `POST` | `/search/answer` | Citation-first grounded answer over the local snapshot (`AnswerRequest`) |

**`/docs` (read exported Markdown / metadata)**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/docs/index` | Full `index.md` from `MD_EXPORT_ROOT` (`DocsIndexResponse`) |
| `GET` | `/docs/catalog` | All pages from DB + `md_relpath` (`DocsCatalogResponse`) |
| `GET` | `/docs/stats` | Page/chunk counts plus source, snapshot, cache, and stale-artifact metadata (`DocsStatsResponse`) |
| `GET` | `/docs/export/file/{file_path}` | Read a file under **export** root (e.g. `guides/structured-outputs.md`); no `..` |
| `GET` | `/docs/raw/file/{file_path}` | Read a file under **raw** cache dir (e.g. `abc123….json`) |

### Example API usage (`curl`)

```bash
BASE=http://localhost:8000

# Health + resolved config (no API key)
curl -s "$BASE/health" | jq
curl -s "$BASE/config" | jq

# Initialize DB (local paths; omit body fields in Docker if env is set)
curl -s -X POST "$BASE/project/init" \
  -H "Content-Type: application/json" \
  -d '{"db_path": "data/docs.sqlite3"}'

# Ingest from cache
curl -s -X POST "$BASE/ingest/cached" \
  -H "Content-Type: application/json" \
  -d '{"db_path": "data/docs.sqlite3", "raw_dir": "data/raw_data", "force": false}'

# Search: FTS only (no OpenAI)
curl -s -X POST "$BASE/search/query" \
  -H "Content-Type: application/json" \
  -d '{"q": "function calling", "no_embed": true, "k": 5}'

# Search: vectors over page summaries (needs OPENAI_API_KEY + page embeddings)
curl -s -X POST "$BASE/search/query" \
  -H "Content-Type: application/json" \
  -d '{"q": "structured outputs", "k": 5, "target": "pages"}'

# Grounded answer with exact citations from the local snapshot
curl -s -X POST "$BASE/search/answer" \
  -H "Content-Type: application/json" \
  -d '{"q": "How does function calling work?", "no_embed": true, "synthesis_mode": "extractive"}'

# Same search via GET
curl -s "$BASE/search/query?q=structured+outputs&k=5&target=pages"

# Navigation index + one export file (path = remainder of URL after /docs/export/file/)
curl -s "$BASE/docs/index" | jq '.path, .bytes_length'
curl -s "$BASE/docs/export/file/guides/structured-outputs.md" | jq '.path, .media_type, (.content | length)'

# Catalog + stats
curl -s "$BASE/docs/catalog" | jq '.count'
curl -s "$BASE/docs/stats" | jq

# Docker: DB_PATH / RAW_DIR already in env — minimal bodies work, e.g.:
# curl -s -X POST "$BASE/ingest/cached" -H "Content-Type: application/json" -d '{}'
```

## Standalone Scripts

All scripts are in the `scripts/` directory:

```bash
# Initialize database
python scripts/init_project.py --db data/docs.sqlite3

# Run a tracked refresh from the current raw cache snapshot
python scripts/run_refresh.py --db data/docs.sqlite3 --raw-dir data/raw_data --sitemap data/sitemap.xml --no-fetch-sitemap

# Ingest cached pages
python scripts/run_ingest.py --db data/docs.sqlite3 --raw-dir data/raw_data

# Generate summaries (requires OPENAI_API_KEY)
python scripts/run_summarize.py --db data/docs.sqlite3 -n 50

# Generate embeddings (requires OPENAI_API_KEY)
python scripts/run_embed.py --db data/docs.sqlite3 --target chunks -n 500

# Search (FTS-only)
python scripts/query.py -q "structured outputs" --no-embed

# Search (with embeddings, requires OPENAI_API_KEY)
python scripts/query.py -q "how do I do function calling?" -k 10
```

## Quick Start

1. **Initialize DB and publish a tracked snapshot from cached data:**
   ```bash
   python scripts/init_project.py
   python scripts/run_refresh.py --no-fetch-sitemap
   ```

2. **Quick keyword search (no OpenAI calls):**
   ```bash
   python scripts/query.py -q "structured outputs" --no-embed
   ```

3. **Enable summaries + vector search:**
   ```bash
   export OPENAI_API_KEY="your-key"
   python scripts/run_summarize.py -n 50
   python scripts/run_embed.py --target chunks -n 500
   python scripts/query.py -q "how do I do function calling?" -k 10
   ```

## Configuration

Set environment variables in `.env`:

```bash
OPENAI_API_KEY=your-key
DB_PATH=data/docs.sqlite3
RAW_DIR=data/raw_data
```

## Quality and Evaluation

The repo now includes a repeatable offline retrieval benchmark and a small automated test suite:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_eval.py
PYTHONPATH=src .venv/bin/python scripts/full_gate_a_smoke.py
```

- Test coverage lives under `tests/` and covers extraction, chunking, FTS trigger sync, safe export-path mapping, and FTS punctuation handling.
- Service-readiness coverage includes API/MCP smoke checks, grounded answers, snapshot metadata, and source adapter behavior.
- The offline benchmark corpus lives under `evals/corpus/raw_pages/`.
- Labeled benchmark queries live under `evals/benchmarks/openai_docs_benchmark.json`.
- The committed reference baseline lives at `evals/results/baseline_local.json`.
- Fresh benchmark runs write `evals/results/latest_local.json` by default.

## Incremental Sync Behavior

Phase 3 change tracking is now in place for the local pipeline:

- unchanged pages are detected by content hash and skipped without re-chunking, re-summarizing, or re-embedding
- changed pages increment `content_version`, record a `page_revisions` row, and leave stale summary or embedding alignment visible through `*_for_hash` fields until downstream jobs refresh them
- pages now track an explicit `page_state` such as `new`, `unchanged`, `changed`, `deleted`, or `failed`
- split-markdown exports also track freshness through `export_for_hash`, so the repo can report when exported docs are stale relative to the latest ingested content
- full refresh runs can mark missing pages as deleted so search, docs catalog, and MCP tools stop returning them
- incremental sync runs can keep missing pages active when the current raw cache is intentionally partial

Examples:

```bash
# Full refresh: treat raw_dir as the authoritative snapshot and mark missing pages deleted
python scripts/run_ingest.py --db data/docs.sqlite3 --raw-dir data/raw_data --full-refresh

# Incremental sync: ingest only what is present and do not prune pages missing from this partial cache
python scripts/run_ingest.py --db data/docs.sqlite3 --raw-dir data/raw_data --incremental
```

API behavior is the same through `POST /ingest/cached` with `mark_missing_deleted: true|false`.

## Refresh Runs and Published Snapshots

Phase 1 of the expansion plan adds a tracked refresh flow for the active source.

- `scripts/run_refresh.py` creates a refresh `run`, ingests the current raw cache into a staged SQLite database, and only publishes that database on success
- `/health`, `/config`, and `/docs/stats` now expose:
  - latest run id and status
  - latest successful run id
  - active snapshot id and publication timestamp
- if a refresh fails, search and grounded answers continue using the previously published database snapshot

## Phase 2 Signals

Phase 2 extends the local ledger so change handling is visible, not implicit.

- `POST /ingest/cached` now reports `pages_failed` and `exports_invalidated`
- `/docs/stats` now reports `pages_failed` and `stale_exports`
- exporting the split markdown bundle marks exported pages fresh against the current `content_hash`
- a later content change makes that export stale until the bundle is rebuilt

## Phase 3 Change Ledger

Phase 3 turns the recorded change state into inspectable history.

- `GET /docs/page/history?url=...` returns revision history for one page
- `GET /docs/page/diff?url=...&from_version=1&to_version=2` returns a unified diff between revisions
- `GET /docs/changes` returns new, changed, and deleted pages for the latest or a named run
- MCP now exposes `get_page_history`, `get_page_diff`, and `get_recent_changes`

## Phase 4 Unattended Operation

Phase 4 hardens the refresh path for cron, systemd, or container timers.

- `scripts/run_refresh.py` now supports:
  - `--trigger`
  - `--lock-path`
  - `--lock-timeout-s`
  - `--log-path`
- only one refresh per source runs at a time; concurrent runs fail fast with a lock error
- stale locks are recovered automatically after the configured timeout
- refresh runs append JSONL events to `data/logs/refresh_runs.jsonl` by default
- CLI exit codes are stable for automation:
  - `0` success
  - `3` lock conflict / skipped because another refresh is active
  - `1` failure

## Grounded Answers

Phase 4 adds a citation-first answer layer on top of retrieval.

- `POST /search/answer` answers from the local snapshot and returns exact citations
- each answer includes cited source URLs, markdown paths, local export paths, and freshness metadata
- warnings surface stale summaries, stale page embeddings, and old snapshots instead of hiding that state
- raw retrieval still exists and remains the lower-level interface

Example:

```bash
curl -s -X POST http://localhost:8000/search/answer \
  -H "Content-Type: application/json" \
  -d '{
    "q": "How does function calling work?",
    "k": 6,
    "citations_limit": 4,
    "fts": true,
    "target": "chunks",
    "no_embed": true,
    "synthesis_mode": "extractive"
  }' | jq
```

The MCP server also exposes `answer_question` for the same citation-first workflow.

## Notes

- Respect `robots.txt`, rate limits, and terms of use.
- Summaries/embeddings are intended for local retrieval ("what guide should I read?"), not as an authoritative replacement for the docs.
