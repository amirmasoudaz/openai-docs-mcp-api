# Project plan: OpenAI Docs Scraper + Vector Search

## Goal

Continuously ingest OpenAI Platform docs pages listed in `https://platform.openai.com/docs/sitemap.xml`, extract their content into a normalized format (prefer markdown), generate a *very short* page summary, embed summaries (and optionally chunks), and provide a local search pipeline to retrieve the best pages for a query.

## Reality check from live probes

- The docs sitemap is accessible and currently lists ~735 unique URLs (no `lastmod` fields).
- In this environment, direct HTTP and Playwright both hit a Cloudflare “managed challenge” for individual doc pages (HTTP 403).

Implication: The scraper must support a **browser-based fetcher** and an **interactive bootstrap** path (where the user completes any challenge in a real browser window). In other environments (e.g., residential IPs), direct HTTP may work and can be added as a fast path.

## Architecture (pipelines + components)

### 1) URL discovery

- Input: `docs/sitemap.xml`
- Output: ordered list of page URLs
- Normalization: de-dupe (sitemap already de-duped), normalize trailing slash, store `url` and `path` and inferred `section` (`guides`, `api-reference`, etc.)

### 2) Fetching (pluggable)

Provide a `Fetcher` interface and at least these implementations:

1. **BrowserFetcher (Playwright + Chrome)**:
   - Uses `storage_state.json` (created by an interactive bootstrap command) if present.
   - Loads URL, waits for the main content container to be present.
   - Returns rendered HTML and optionally a “content extraction handle” (DOM context).
2. **HttpFetcher (httpx)** (optional fast path):
   - Used only when requests succeed without challenges.
   - Supports `ETag` / `If-Modified-Since` when available.

### 3) Extraction (prefer markdown)

Implement extraction with a tiered strategy:

1. **Copy-page markdown capture** (preferred):
   - Many OpenAI docs pages include “Copy page” that copies markdown to clipboard.
   - In Playwright, click the button and capture the markdown without needing OS clipboard by instrumenting `navigator.clipboard.writeText` inside the page.
2. **DOM extraction + HTML→Markdown fallback**:
   - Select the main article container (by role/semantic selectors).
   - Remove nav/aside/footer.
   - Convert remaining HTML to markdown (or at least to clean plain text).

Outputs per page:

- `raw_markdown` (best-effort)
- `plain_text` (for FTS + chunking)
- `title` (from `<title>` and/or first H1)
- `content_hash` (sha256 of normalized markdown)

### 4) Summarization

For each page whose `content_hash` changed (or missing summary):

- Prompt: produce a *very short* summary (1–3 sentences, no fluff, include what the page is for).
- Store: `summary`, `summary_model`, `summary_updated_at`, `summary_hash`.

### 5) Chunking (recommended)

Chunking improves retrieval over long pages:

- Split by markdown headings when possible; otherwise by paragraph.
- Enforce max chunk size (token or character based) with overlap.
- Store per-chunk `heading_path`, `chunk_text`, `chunk_hash`.

### 6) Embeddings

- Embed page summaries for page-level retrieval.
- Embed chunks for high-recall retrieval.
- Store normalized float32 vectors.

### 7) Storage and indexing

Use SQLite for portability + auditability:

- `pages`: one row per URL (raw content + summary + page embedding)
- `chunks`: one row per chunk (chunk text + chunk embedding)
- `chunks_fts` (FTS5): keyword search over `chunk_text`

Vector search:

- For small-to-medium corpora: load candidate embeddings into memory and compute cosine similarity in Python.
- Optional future upgrade: add FAISS or a vector DB backend (LanceDB/Qdrant) behind an interface.

### 8) Query pipeline

Given a user query:

1. Embed query.
2. Retrieve top `K` chunks by cosine similarity.
3. Group by page URL and score aggregate (e.g., max or sum of top-N chunk scores).
4. Return top pages with `url`, `title`, `summary`, and a few best-matching chunk snippets.
5. Optional: LLM reranking of top 20 with a short cost-controlled prompt.

## Operational concerns (make it “continuous”)

- **Change detection**: sitemap has no `lastmod`; rely on `content_hash` and skip unchanged pages.
- **Crawl budget**: throttle concurrency; exponential backoff on errors.
- **Resumability**: store per-URL scrape status and last attempt time; allow `--resume`.
- **Versioning**: keep historical snapshots optionally (append-only table or `pages_history`).
- **Compliance**: respect `robots.txt`, identify with a UA string, and keep request volume reasonable.

## Deliverables (implementation checklist)

1. CLI skeleton (already started): sitemap fetch/list, DB init, browser bootstrap.
2. `Fetcher` interface + `BrowserFetcher` with persisted state.
3. Markdown capture from “Copy page” (instrumented clipboard).
4. HTML→Markdown fallback extractor and plain text normalization.
5. SQLite upserts for pages/chunks, plus FTS sync.
6. Summarize + embed workers with batching, caching, retry.
7. Query command with vector + optional hybrid (FTS + vector).
8. End-to-end runbook: “bootstrap → ingest → query”.

## Validation plan (what to test)

- Unit tests:
  - sitemap parsing returns correct URL counts and de-dupes.
  - chunking produces stable chunk boundaries for sample markdown.
  - embedding serialization round-trips.
  - DB triggers keep FTS in sync on insert/update/delete.
- Integration tests (manual / environment-dependent):
  - Browser bootstrap + single-page scrape on a known URL.
  - Extracted markdown is non-empty and contains expected headings.
  - Summaries are short and consistent.
  - Query returns relevant guides for example prompts:
    - “How do I do structured outputs?”
    - “How do I use function calling in Responses API?”
    - “What’s the right way to do embeddings + retrieval?”

