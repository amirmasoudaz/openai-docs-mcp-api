# LLM Provider Docs Ledger Architecture

This repo is a local-first documentation retrieval system with four main layers:

1. Acquisition
   - sitemap discovery
   - browser-backed page capture into raw JSON cache files

2. Processing
   - HTML extraction and normalization
   - chunking
   - SQLite storage with FTS5
   - optional summaries and embeddings

3. Serving
   - CLI scripts
   - FastAPI routes
   - Markdown export tree
   - MCP tools

4. Grounded use
   - retrieval
   - citation-first answers
   - snapshot and artifact-state reporting

## Current service seams

- source adapter boundary in `src/openai_docs_scraper/sources/`
- retrieval and answer services in `src/openai_docs_scraper/services/`
- artifact-state inspection in `src/openai_docs_scraper/services/state.py`
- API contracts in `src/openai_docs_scraper/api/`

## Path to service mode later

The repo is still optimized for local-first use, but the current seams support a later service deployment path:

1. Keep acquisition as a job boundary.
2. Keep ingestion, summarization, and embedding as background-task boundaries.
3. Treat SQLite as the current metadata store and retrieval index, not as a permanent assumption.
4. Keep API and MCP surfaces stable while storage and job execution evolve behind them.

The next service step should be job orchestration and snapshot management, not premature distributed infrastructure.
