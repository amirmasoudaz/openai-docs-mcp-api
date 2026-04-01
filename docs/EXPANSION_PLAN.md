# Expansion Plan

This document is the realistic next-stage plan for expanding `llm-provider-docs-ledger` into a continuously refreshed, multi-provider documentation ledger while keeping the project local-first. The goal is not to build a hosted pipeline-as-a-service yet; the goal is to make the existing system update reliably, track changes over time, and support additional providers behind the same ingestion and retrieval architecture.

## Goals

1. Keep the OpenAI corpus fresh with frequent, repeatable refresh runs.
2. Detect new, changed, and removed pages without rebuilding everything every time.
3. Preserve a useful ledger of documentation changes over time.
4. Add additional provider adapters without forking the core pipeline.
5. Keep search, export, and grounded answers in sync with the latest successful snapshot.

## Non-goals

- Building a hosted multi-tenant service.
- Replacing SQLite immediately.
- Adding auth, billing, or shared deployment infrastructure.
- Supporting arbitrary websites before the provider adapter model is proven.

## Success criteria

- A scheduled refresh can run unattended and finish cleanly for the active providers.
- Unchanged pages are skipped cheaply; changed pages trigger selective downstream recompute.
- The system can report:
  - when a page was first seen
  - when it last changed
  - what changed in the latest run
  - which pages are stale, failed, or deleted
- OpenAI, Anthropic, and Perplexity can all run through the same top-level workflow with provider-specific adapters.
- Search and grounded answers default to the latest successful snapshot and do not serve half-finished runs.

## How we achieve this

The path is to formalize three things that are still partly implicit today:

1. `runs`
   - every refresh attempt becomes a tracked run with status, timestamps, and counts
2. `snapshots`
   - retrieval and export should resolve against a latest successful snapshot, not whatever was last partially written
3. `source adapters`
   - provider-specific discovery, normalization, and URL rules stay isolated behind the adapter boundary

Once those are first-class, the rest becomes predictable:

- discover URLs on a schedule
- fetch only what is new or worth checking
- normalize and hash content
- record page/version changes
- selectively rerun chunking, summaries, embeddings, and export
- publish a new snapshot only after required stages succeed

## Phase 1: OpenAI recurring refresh foundation

### Objective

Turn the current OpenAI pipeline into a repeatable scheduled workflow with tracked runs and safe publication of the latest successful snapshot.

### Status

Done

### Deliverables

- SQLite tables for:
  - `sources`
  - `runs`
  - `snapshots`
- a single entrypoint script for a full refresh cycle
- source-level run summaries in API and CLI status surfaces
- a clear distinction between:
  - in-progress run
  - failed run
  - latest successful snapshot

### Milestones

1. Add a run ledger schema and source registry.
2. Add a top-level refresh command such as `scripts/run_refresh.py`.
3. Update health/stats responses to expose run and snapshot status.
4. Ensure retrieval resolves against the latest successful snapshot.

### Likely touchpoints

- `src/openai_docs_scraper/db.py`
- `src/openai_docs_scraper/services/state.py`
- `src/openai_docs_scraper/services/project.py`
- `src/openai_docs_scraper/api/routes/`
- `scripts/`

### Acceptance criteria

- One command can execute a tracked OpenAI refresh from discovery through publish.
- If a run fails midway, the previously published snapshot remains the default for search and answers.

## Phase 2: Change detection and selective recompute

### Objective

Stop treating every refresh like a rebuild. Detect what actually changed and recompute only the affected downstream artifacts.

### Status

Done

### Deliverables

- per-page version records
- normalized content hashes
- explicit page states:
  - new
  - unchanged
  - changed
  - deleted
  - failed
- stale-artifact invalidation tied to page changes

### Milestones

1. Add `page_versions` and page-state tracking.
2. Hash normalized content, not only raw HTML.
3. Mark summaries, page embeddings, chunk embeddings, and exports stale only for changed pages.
4. Add CLI/API reporting for changed and deleted pages in the latest run.

### Likely touchpoints

- `src/openai_docs_scraper/db.py`
- `src/openai_docs_scraper/services/ingestion.py`
- `src/openai_docs_scraper/ingest_cached.py`
- `src/openai_docs_scraper/services/summarizer.py`
- `src/openai_docs_scraper/services/embedder.py`
- `src/openai_docs_scraper/book_export.py`

### Acceptance criteria

- Refreshing an unchanged corpus performs little or no downstream recompute.
- A changed page causes only its dependent artifacts to be regenerated.

## Phase 3: Change ledger and diff visibility

### Objective

Make documentation changes inspectable instead of opaque.

### Status

Done

### Deliverables

- latest-run change summary
- page history view
- section-aware or markdown-level diff output
- exportable change report for provider updates

### Milestones

1. Add a page history API/CLI view.
2. Add a diff routine based on normalized markdown.
3. Generate a run-level change report containing:
   - new pages
   - removed pages
   - materially changed pages
4. Expose change metadata through MCP so agents can ask what changed recently.

### Likely touchpoints

- `src/openai_docs_scraper/services/state.py`
- `src/openai_docs_scraper/api/routes/docs.py`
- `src/openai_docs_scraper/mcp_server.py`
- new diff/report helpers under `src/openai_docs_scraper/services/`

### Acceptance criteria

- For any tracked page, the repo can show when it changed and what changed.
- A user can inspect the latest provider-doc changes without manually diffing raw cache files.

## Phase 4: Scheduler and unattended operation

### Objective

Run refreshes regularly without manual babysitting.

### Status

Done

### Deliverables

- scheduler-friendly refresh command with exit codes
- source-specific cadence configuration
- lock or lease mechanism to prevent overlapping runs
- retry policy for fetch and processing failures
- run logs and basic failure classification

### Milestones

1. Add scheduler config to settings.
2. Add lock handling so only one refresh per source runs at a time.
3. Add structured run logging.
4. Document cron, systemd, and container scheduling options.

### Recommended cadence

- sitemap/index discovery: every 15 to 30 minutes
- targeted page refresh: every 1 to 4 hours
- full source reconciliation: daily
- full integrity sweep and eval run: weekly

### Likely touchpoints

- `src/openai_docs_scraper/services/config.py`
- `src/openai_docs_scraper/services/scraper.py`
- `scripts/`
- `docker-compose.yml`
- `docs/PROJECT_GUIDE.md`

### Acceptance criteria

- The project can be run unattended on one machine and recover cleanly from transient failures.
- A stalled or failed run does not corrupt the published snapshot state.

## Phase 5: Anthropic adapter

### Objective

Prove that the adapter boundary works by adding a second provider with a different documentation structure.

### Deliverables

- `anthropic_docs` source adapter
- provider-specific discovery and normalization rules
- source fixture corpus and adapter tests
- refresh and search support for Anthropic snapshots

### Milestones

1. Implement URL normalization and export mapping for Anthropic docs.
2. Add provider-specific scrape/extract fixtures.
3. Run the same refresh workflow against Anthropic.
4. Add provider-aware status and catalog reporting.

### Likely touchpoints

- `src/openai_docs_scraper/sources/`
- `src/openai_docs_scraper/extract.py`
- `tests/`
- `evals/`

### Acceptance criteria

- Anthropic docs can be refreshed and searched without special-case pipeline code outside the adapter.

## Phase 6: Perplexity adapter

### Objective

Validate the multi-provider shape with a third provider and expose any assumptions that still leak from the OpenAI-first implementation.

### Deliverables

- `perplexity_docs` source adapter
- provider-specific fixtures and tests
- source-level catalog and search filtering

### Milestones

1. Implement Perplexity adapter defaults and extraction rules.
2. Add fixtures for representative pages.
3. Run refresh, export, and retrieval validation for Perplexity.
4. Fix any remaining OpenAI-specific assumptions in shared code.

### Acceptance criteria

- OpenAI, Anthropic, and Perplexity all run through the same top-level workflow with only adapter-specific logic differing.

## Phase 7: Multi-provider retrieval polish

### Objective

Make the search and answer experience clean once multiple providers are present.

### Deliverables

- source filtering in query APIs and MCP tools
- result grouping or diversification by source
- canonical dedupe for alias-like pages
- ranking features that account for:
  - exact model names
  - quickstart or onboarding intent
  - canonical guide preference
  - deprecated-page penalties

### Milestones

1. Add `source` and `snapshot` filters to query and answer requests.
2. Add dedupe for alias-equivalent pages.
3. Add multi-provider eval queries and baselines.
4. Tune ranking with provider-aware and page-type-aware priors.

### Acceptance criteria

- Adding more providers improves coverage without making search noisier.
- Grounded answers cite the right provider and the right canonical guide first.

## Phase 8: Reliability and quality gates

### Objective

Keep the expanding system trustworthy as it gets more automated.

### Deliverables

- end-to-end refresh smoke test
- provider-specific extraction regression tests
- scheduled eval runs and saved reports
- documented failure playbooks for:
  - sitemap breakage
  - HTML structure changes
  - anti-bot or auth failures
  - partial refresh failures

### Milestones

1. Expand the smoke gate to exercise refresh publication and change detection.
2. Save eval reports per provider and per snapshot.
3. Add alertable failure categories in run status.
4. Document recovery workflows.

### Acceptance criteria

- A broken provider adapter or fetch step is visible quickly and does not silently poison the published corpus.

## Recommended implementation order

1. Phase 1: OpenAI recurring refresh foundation
2. Phase 2: Change detection and selective recompute
3. Phase 3: Change ledger and diff visibility
4. Phase 4: Scheduler and unattended operation
5. Phase 5: Anthropic adapter
6. Phase 6: Perplexity adapter
7. Phase 7: Multi-provider retrieval polish
8. Phase 8: Reliability and quality gates

## Practical risks and bottlenecks

### 1. Acquisition brittleness

Provider docs can change sitemap layout, HTML structure, rate limits, or anti-bot behavior at any time. This is the main operational risk.

### 2. Canonicalization drift

The same content may appear under multiple URLs, migration pages, aliases, or old/new guides. Without canonical grouping, search quality degrades quickly.

### 3. False-positive change detection

If hashing is tied too closely to raw HTML instead of normalized content, minor template changes will trigger unnecessary recompute.

### 4. Expensive downstream processing

Summaries and embeddings are the costly stages. If invalidation is too broad, refresh cycles become slow and expensive.

### 5. Multi-provider retrieval noise

Once multiple providers exist, ranking, dedupe, and source selection matter more. Search quality can regress even if ingestion works.

## Definition of done for this expansion

- OpenAI refreshes automatically and publishes stable snapshots.
- New, changed, and deleted pages are tracked explicitly.
- The system can answer “what changed?” for a provider without manual inspection.
- Anthropic and Perplexity are both onboarded through adapters.
- Search and grounded answers stay usable as the corpus expands.

## Suggested milestone checkpoints

### Milestone A

OpenAI unattended refresh is stable.

### Milestone B

OpenAI change ledger and selective recompute are stable.

### Milestone C

Anthropic is live through the shared pipeline.

### Milestone D

Perplexity is live through the shared pipeline.

### Milestone E

Multi-provider retrieval quality is good enough for daily use.
