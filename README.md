# openai-docs-scraper

Scrape `https://platform.openai.com/docs/sitemap.xml`, extract each page's content (prefer markdown when available), generate a *very short* per-page summary + embedding, and provide local search over the corpus.

**Full operations guide** (pipelines, API/MCP, Docker, updating data, GitHub publishing): [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md).

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
- **OpenAI:** `POST /process/summarize`, `POST /process/embed`, and **vector** search (`/search/query` with `no_embed: false`) need **`OPENAI_API_KEY`**. FTS-only search (`no_embed: true`) does not.

### API endpoints (full list)

**App root**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness; includes `db_exists`, `index_md_exists`, resolved paths |
| `GET` | `/config` | Non-secret defaults: `db_path`, `md_export_root`, `raw_dir`, `embedding_model`, `summary_model` |

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
| `POST` | `/ingest/cached` | Read `raw_dir` JSON → SQLite + chunks (`IngestRequest`) |

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

**`/docs` (read exported Markdown / metadata)**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/docs/index` | Full `index.md` from `MD_EXPORT_ROOT` (`DocsIndexResponse`) |
| `GET` | `/docs/catalog` | All pages from DB + `md_relpath` (`DocsCatalogResponse`) |
| `GET` | `/docs/stats` | Page/chunk counts, embedding coverage (`DocsStatsResponse`) |
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

1. **Initialize DB and ingest cached data:**
   ```bash
   python scripts/init_project.py
   python scripts/run_ingest.py
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

## Notes

- Respect `robots.txt`, rate limits, and terms of use.
- Summaries/embeddings are intended for local retrieval ("what guide should I read?"), not as an authoritative replacement for the docs.
