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

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/project/init` | Initialize database |
| `POST` | `/project/sitemap/fetch` | Fetch sitemap XML |
| `POST` | `/project/sitemap/list` | List sitemap URLs |
| `POST` | `/scrape/run` | Run scraping job |
| `POST` | `/ingest/cached` | Ingest cached pages |
| `POST` | `/process/summarize` | Generate summaries |
| `POST` | `/process/embed` | Generate embeddings |
| `GET/POST` | `/search/query` | Execute search |
| `GET` | `/health` | Health check |

### Example API Usage

```bash
# Initialize database
curl -X POST http://localhost:8000/project/init \
  -H "Content-Type: application/json" \
  -d '{"db_path": "data/docs.sqlite3"}'

# Ingest cached pages
curl -X POST http://localhost:8000/ingest/cached \
  -H "Content-Type: application/json" \
  -d '{"db_path": "data/docs.sqlite3", "raw_dir": "data/raw_data"}'

# Search (FTS-only, no API key needed)
curl -X POST http://localhost:8000/search/query \
  -H "Content-Type: application/json" \
  -d '{"q": "function calling", "no_embed": true}'

# Or use GET:
curl "http://localhost:8000/search/query?q=embeddings&no_embed=true&k=5"
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
