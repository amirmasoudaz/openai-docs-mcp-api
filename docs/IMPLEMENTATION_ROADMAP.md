# Implementation Roadmap

This document is the tracked execution plan for turning `openai-docs-scraper` from a strong local retrieval utility into a differentiated, measured, agent-ready documentation platform. It is intentionally phase-based so work can land incrementally without losing the long-term shape.

This roadmap assumes:

- The product remains **local-first** for now.
- SQLite, file exports, CLI, API, and MCP remain first-class interfaces.
- The next major quality bar is **measured retrieval performance**, not feature volume.
- Service-readiness should emerge from cleaner boundaries and validation, not from premature infrastructure swaps.

## How to use this file

- Update phase status as work starts and finishes.
- Check off tasks as they land.
- Add implementation notes and benchmark results to the relevant phase.
- Keep scope changes explicit in this file so the roadmap stays trustworthy.

## Status legend

- `Not started`
- `In progress`
- `Blocked`
- `Done`

## Program goals

1. Make the project clearly differentiated as an **agent-ready documentation retrieval system** rather than a generic scraper.
2. Make retrieval quality **measurable** and use those measurements to drive ranking decisions.
3. Make acquisition, ingestion, and export **more reliable and observable**.
4. Add a grounded answer layer with **strict citation discipline** and freshness metadata.
5. Refactor source-specific assumptions so the platform can later support more than OpenAI docs.
6. Leave the codebase in a shape that can evolve into a shared service later without a rewrite.

## Non-goals for this roadmap

- Building a multi-tenant hosted service in this pass.
- Replacing SQLite before local-first limits are actually reached.
- Adding speculative infrastructure that is not justified by evaluation data.
- Expanding to many sources before the adapter boundary is clean.

## Phase order

| Phase | Name | Primary outcome | Status |
|------|------|-----------------|--------|
| 1 | Evaluation + Quality Baseline | Measured retrieval and parser quality | Done |
| 2 | Ranking + Retrieval Improvements | Better search quality backed by eval data | Done |
| 3 | Incremental Sync + Change Tracking | Selective refresh and stale-artifact invalidation | Done |
| 4 | Grounded Answer Layer | Citation-first answers over local snapshots | Done |
| 5 | Source Abstraction | Source adapters separated from core pipeline | Done |
| 6 | Service-Ready Evolution Prep | Clear seams for later shared deployment | Done |

## Global definition of done

- Retrieval modes have benchmark coverage with tracked results.
- Ingestion and export correctness have repeatable automated tests.
- Ranking changes are made against eval baselines, not intuition alone.
- Incremental refresh avoids unnecessary recompute and marks stale artifacts explicitly.
- Answer generation cites exact local files and exposes snapshot freshness.
- OpenAI-specific logic is isolated behind source adapters.
- The repo documentation explains the system in product and architecture terms.

---

## Phase 1: Evaluation + Quality Baseline

**Status:** Done

### Goal

Create the measurement layer and parser-quality safety net that the rest of the roadmap will depend on.

### Why this phase comes first

Without benchmarks and ingestion tests, later ranking and answer-generation work will be mostly cosmetic. This phase establishes what “better” means and prevents regressions.

### Deliverables

- A retrieval evaluation dataset with labeled queries and expected URLs or chunks.
- An eval runner that compares FTS-only, page-vector, chunk-vector, and hybrid retrieval.
- Standard metrics including recall@k, MRR, and hit-rate by query set.
- Fixture-driven ingestion tests for extraction and chunking behavior.
- Baseline benchmark output committed to the repo.

### Likely file and module changes

- Add `evals/benchmarks/` for query datasets and expected results.
- Add `scripts/run_eval.py` or similar for repeatable benchmark runs.
- Add `tests/` with unit and fixture tests for extraction, chunking, DB triggers, and export mapping.
- Touch [src/openai_docs_scraper/extract.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/extract.py).
- Touch [src/openai_docs_scraper/ingest_cached.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/ingest_cached.py).
- Touch [src/openai_docs_scraper/db.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/db.py).
- Touch [src/openai_docs_scraper/book_export.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/book_export.py).

### Acceptance criteria

- At least 30 to 50 benchmark queries exist across guides, API patterns, models, tools, and platform workflows.
- Benchmark runs produce a machine-readable results artifact.
- FTS, page-level semantic search, chunk-level semantic search, and hybrid search can all be evaluated through one command.
- Tests cover code block preservation, heading hierarchy, chunk boundaries, duplicate-page handling, export path stability, and FTS trigger correctness.
- A baseline results section is added to this document or a companion eval report.

### Validation

- `pytest -q`
- `python scripts/run_eval.py`
- `python -m compileall src`

### Risks and notes

- Eval labels can drift as the docs evolve; benchmark fixtures need snapshot-awareness.
- Query coverage should favor real developer intents, not synthetic search phrases.
- Tests should use representative HTML fixtures rather than overly simplified snippets.

### Tracking checklist

[x] Create the `tests/` directory and basic `pytest` configuration.
[x] Add HTML and Markdown fixtures for representative docs pages.
[x] Add parser and chunking tests.
[x] Add FTS trigger sync tests.
[x] Add export-path and canonical-markdown mapping tests.
[x] Create the first benchmark dataset.
[x] Implement the eval runner.
[x] Commit baseline retrieval results.

### Implementation notes

- Use the current exported markdown and DB schema as the baseline behavior rather than redesigning the pipeline in this phase.
- Keep the first benchmark format simple: `query`, `target`, `expected_urls`, `expected_md_paths`, `notes`.

---

## Phase 2: Ranking + Retrieval Improvements

**Status:** Done

### Goal

Improve search quality using measured ranking logic rather than raw cosine similarity or raw BM25 alone.

### Deliverables

- A unified ranking layer that can combine lexical and semantic signals.
- Tunable ranking weights with benchmark-based comparison against the Phase 1 baseline.
- Better result grouping and page-level de-duplication behavior.
- Optional structured snippets showing why a result matched.

### Likely file and module changes

- Touch [src/openai_docs_scraper/search.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/search.py).
- Touch [src/openai_docs_scraper/services/search.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/services/search.py).
- Add a ranking module such as `src/openai_docs_scraper/ranking.py`.
- Extend API schemas in [src/openai_docs_scraper/api/schemas.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/api/schemas.py) if ranking diagnostics are exposed.

### Acceptance criteria

- Ranking combines at least lexical score, vector score, and one structural prior.
- Benchmarks show a measurable lift over the Phase 1 baseline on at least one primary metric.
- Retrieval behavior for exact technical terms remains strong and does not regress under semantic tuning.
- Grouped results still preserve useful chunk-level evidence.

### Candidate ranking signals

- FTS/BM25 score
- vector similarity
- exact query-term match bonus
- title match boost
- heading-path match boost
- section or path prior
- chunk position prior

### Validation

- `pytest -q`
- `python scripts/run_eval.py --compare-baseline`
- manual spot checks for exact-term queries and conceptual queries

### Risks and notes

- Weighted heuristics can overfit a small benchmark set.
- Summary-based page retrieval is useful for routing but can hide fine-grained details if given too much weight.
- Ranking diagnostics should be inspectable so changes are explainable.

### Tracking checklist

[x] Extract ranking logic into a dedicated module.
[x] Add hybrid ranking path to the search service.
[x] Add exact-term and title/heading boosts.
[x] Add per-hit signal diagnostics for local debugging.
[x] Tune weights against benchmark results.
[x] Record post-tuning benchmark deltas.

---

## Phase 3: Incremental Sync + Change Tracking

**Status:** Done

### Goal

Move from mostly snapshot refreshes to selective updates with explicit stale-artifact handling.

### Deliverables

- Content diffing at page and chunk level.
- Selective re-ingestion and re-embedding for changed pages only.
- Stale summary and embedding invalidation when source content changes.
- Optional revision history for debugging and export provenance.
- Refresh commands that clearly distinguish full rebuild from incremental sync.

### Likely file and module changes

- Touch [src/openai_docs_scraper/db.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/db.py).
- Touch [src/openai_docs_scraper/services/ingestion.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/services/ingestion.py).
- Touch [src/openai_docs_scraper/ingest_cached.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/ingest_cached.py).
- Touch [src/openai_docs_scraper/services/summarizer.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/services/summarizer.py).
- Touch [src/openai_docs_scraper/services/embedder.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/services/embedder.py).
- Touch refresh scripts in `scripts/`.

### Proposed schema additions

- `pages.content_version` or equivalent revision marker
- `pages.changed_at`
- `pages.snapshot_id` or crawl generation identifier
- optional `page_revisions` table for historical diffs
- explicit stale markers for summary and embedding alignment

### Acceptance criteria

- A no-op refresh does not re-summarize or re-embed unchanged content.
- A changed page invalidates only the dependent summaries, embeddings, and chunks affected by that change.
- Incremental sync output clearly reports changed, unchanged, invalidated, and refreshed counts.
- Export rebuild can run incrementally or explain why a full rebuild is needed.

### Validation

- `pytest -q`
- repeated ingest on unchanged fixtures shows no unnecessary writes
- changed fixture updates trigger only expected downstream invalidations
- benchmark rerun after incremental sync produces consistent outputs

### Risks and notes

- Change tracking adds schema complexity; keep the first version easy to reason about.
- Revision history can grow quickly if raw HTML snapshots are stored aggressively.
- Chunk-level invalidation logic must align with chunk-hash semantics or it will create hard-to-debug drift.

### Tracking checklist

[x] Design and implement the change-tracking schema.
[x] Add per-page and per-chunk diff detection.
[x] Invalidate stale summaries when content changes.
[x] Invalidate stale embeddings when source text changes.
[x] Add incremental sync CLI/API paths.
[x] Add tests for unchanged, changed, and deleted-page scenarios.
[x] Document full vs incremental refresh behavior.

### Implementation notes

- `pages` now tracks `content_version`, `changed_at`, `last_seen_at`, `last_seen_run_id`, `deleted_at`, and `deletion_reason`.
- `page_revisions` records observed versions for debugging and provenance.
- Search, docs catalog/stats, summarization, embedding, and MCP catalog/stats all ignore pages marked deleted.
- The ingest path now exposes explicit full-refresh vs incremental-sync behavior through `mark_missing_deleted` and the CLI `--incremental` flag.

### Validation snapshot

- `./.venv/bin/pytest -q`
- `python -m compileall src`
- `.venv/bin/python scripts/run_eval.py --compare-baseline`

---

## Phase 4: Grounded Answer Layer

**Status:** Done

### Goal

Add answer synthesis on top of the retrieval stack without sacrificing traceability or overstating certainty.

### Deliverables

- A retrieval-then-synthesize answer service.
- Exact citations to local markdown files and, where possible, heading-level anchors or chunk paths.
- Snapshot freshness metadata in responses.
- Warnings when answers rely on a stale or incomplete local snapshot.
- API and MCP interfaces for grounded Q&A.

### Likely file and module changes

- Add `src/openai_docs_scraper/services/answering.py`.
- Touch [src/openai_docs_scraper/api/routes/search.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/api/routes/search.py) or add a dedicated answer route.
- Touch [src/openai_docs_scraper/mcp_server.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/mcp_server.py).
- Extend schemas in [src/openai_docs_scraper/api/schemas.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/api/schemas.py).

### Response requirements

- include answer text
- include cited markdown file paths
- include cited source URLs
- include snapshot timestamp or generation identifier
- include freshness or staleness warning when appropriate
- avoid unsupported claims when evidence is weak

### Acceptance criteria

- Every generated answer returns citations to exact local artifacts.
- The system can answer from local docs without pretending to know beyond the snapshot.
- Citation paths are resolvable through the docs API and MCP file-read tools.
- The answer layer is optional and does not replace raw retrieval access.

### Validation

- `pytest -q`
- integration tests for answer shape and citation presence
- manual checks with known queries such as function calling, structured outputs, and embeddings

### Risks and notes

- A polished answer layer can mask retrieval errors if citation quality is not enforced.
- The answer service should not silently drop uncertainty; it must degrade explicitly.
- Freshness metadata matters because the live OpenAI docs change often.

### Tracking checklist

[x] Define the answer response schema.
[x] Implement retrieval-to-citation selection.
[x] Implement answer synthesis with strict citation requirements.
[x] Add snapshot freshness metadata.
[x] Add stale-snapshot warnings.
[x] Expose the answer layer through API.
[x] Expose the answer layer through MCP.
[x] Add integration tests for answer citations.

### Implementation notes

- `services/answering.py` now packages retrieval hits into exact citation objects with local file paths and source URLs.
- The answer layer supports `auto`, `openai`, and `extractive` synthesis modes so offline tests and local use remain possible.
- Freshness metadata is derived from cited pages and warns when summaries or page embeddings are stale relative to current content.
- The answer surface is additive: raw retrieval through search remains the lower-level interface.

### Validation snapshot

- `./.venv/bin/pytest -q`
- `python -m compileall src`
- `.venv/bin/python scripts/run_eval.py --compare-baseline`

---

## Phase 5: Source Abstraction

**Status:** Done

### Goal

Separate OpenAI-specific acquisition and normalization logic from the core retrieval platform.

### Deliverables

- A source adapter interface for sitemap discovery, page fetching, normalization, and canonical path generation.
- OpenAI docs implemented as one adapter.
- Core ingestion, indexing, export, and retrieval services no longer hard-coded to a single source.
- Documentation that explains how a second source would plug in later.

### Likely file and module changes

- Add `src/openai_docs_scraper/sources/`.
- Refactor [src/openai_docs_scraper/sitemap.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/sitemap.py).
- Refactor [src/openai_docs_scraper/browser.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/browser.py).
- Refactor [src/openai_docs_scraper/selenium_fetcher.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/selenium_fetcher.py).
- Refactor [src/openai_docs_scraper/book_export.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/book_export.py).
- Refactor scripts that currently assume OpenAI-specific paths or URL rules.

### Acceptance criteria

- Core services can operate through a source adapter contract rather than OpenAI-only helpers.
- Canonical markdown export is generated through source-specific path rules, not global conditionals.
- The OpenAI adapter passes all existing tests after refactor.
- The docs include a clear “how to add a new source” section.

### Validation

- `pytest -q`
- eval suite still passes against the OpenAI adapter
- manual export and retrieval sanity checks still work

### Risks and notes

- Refactoring too early into generic abstractions can create complexity without value.
- Keep the first adapter contract narrow and proven by the existing OpenAI flow.
- Do not add a second source in this phase unless the adapter boundary is already stable.

### Tracking checklist

[x] Define the source adapter interfaces.
[x] Move OpenAI-specific URL and path logic into an adapter.
[x] Move fetch and extraction assumptions behind the adapter boundary.
[x] Refactor export mapping to use the adapter.
[x] Update scripts and services to accept a configured source.
[x] Document how a second source would be added later.

### Implementation notes

- `src/openai_docs_scraper/sources/` now owns the adapter contract, registry, and the `openai_docs` implementation.
- Core helpers such as URL normalization, section inference, sitemap defaults, and export-path mapping now resolve through the configured source adapter.
- The refactor is intentionally narrow: it establishes the boundary without forcing a speculative multi-source implementation in the same phase.

### Validation snapshot

- `./.venv/bin/pytest -q`
- `python -m compileall src`
- `.venv/bin/python scripts/run_eval.py --compare-baseline`

---

## Phase 6: Service-Ready Evolution Prep

**Status:** Done

### Goal

Prepare the local-first system to evolve into a small-team or hosted service later, without actually building the hosted service in this phase.

### Deliverables

- Cleaner configuration and storage seams.
- Better API contracts and operational health endpoints.
- Explicit artifact versioning and snapshot metadata in responses.
- A documented path for moving from local SQLite to a service-capable storage model later if needed.
- CI or local quality gates that reflect product quality, not just syntax.

### Likely file and module changes

- Touch [src/openai_docs_scraper/services/config.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/services/config.py).
- Touch [src/openai_docs_scraper/api/main.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/api/main.py).
- Touch [src/openai_docs_scraper/api/routes/project.py](/home/namiral/Projects/Playground/openai-docs-scraper/src/openai_docs_scraper/api/routes/project.py).
- Touch Docker and script entrypoints.
- Add CI workflows or local gate scripts.

### Acceptance criteria

- Health and stats endpoints expose enough metadata to debug snapshot and artifact state.
- Core services are shaped so a future storage backend swap would be localized rather than invasive.
- Local smoke tests cover API, MCP, export, and retrieval behavior.
- Documentation describes the path from local-first to service-ready architecture.

### Validation

- `pytest -q`
- API smoke test
- MCP smoke test
- Docker compose smoke test
- end-to-end ingest -> search -> export -> answer check

### Risks and notes

- “Service-ready” should not become an excuse for speculative complexity.
- Keep the local developer experience excellent; that is still the product today.
- Any future backend abstraction should be justified by actual operational pain or product need.

### Tracking checklist

[x] Add stronger health and artifact-state reporting.
[x] Add a local or CI quality gate.
[x] Add end-to-end smoke tests for API and MCP.
[x] Document the local-first to service-ready evolution path.
[x] Review storage seams and identify the minimum set of interfaces needed for future backend swaps.

### Implementation notes

- `services/state.py` now centralizes artifact and snapshot metadata so API and MCP stats surfaces stay aligned.
- `scripts/full_gate_a_smoke.py` exercises a complete local product slice across API, retrieval, answers, docs stats, and MCP tools.
- `docs/ARCHITECTURE.md` records the current seams that matter for a later service deployment.

---

## Cross-phase cleanup and documentation

[x] Add `docs/ARCHITECTURE.md`.
[x] Add an eval report template under `docs/`.
[ ] Update [README.md](/home/namiral/Projects/Playground/openai-docs-scraper/README.md) as each major phase lands.
[ ] Update [docs/PROJECT_GUIDE.md](/home/namiral/Projects/Playground/openai-docs-scraper/docs/PROJECT_GUIDE.md) to reflect new workflows and commands.
[ ] Record benchmark deltas after every ranking or ingestion change.

## Suggested execution order

1. Complete Phase 1 before starting substantive ranking changes.
2. Complete the core of Phase 2 before building the answer layer.
3. Land Phase 3 before broadening source support.
4. Land Phase 5 before implementing a second source.
5. Treat Phase 6 as cleanup and architecture hardening, not as a rewrite.

## Progress log

### 2026-03-30

- Created this roadmap.
- Confirmed the near-term strategy:
  - retrieval evaluation and parser tests first
  - ranking second
  - incremental sync third
  - grounded answer generation fourth
  - source abstraction fifth
  - service-ready evolution prep sixth
- Completed Phase 1 foundations:
  - added `pytest` scaffolding and an initial automated test suite, now at 12 passing tests
  - added an offline eval corpus with 30 labeled queries
  - added `scripts/run_eval.py` and committed `evals/results/baseline_local.json`
  - fixed FTS punctuation handling for model names like `gpt-4.1`
  - fixed markdown export path generation for dotted slugs like `gpt-4.1`
- Completed Phase 2 ranking work:
  - added `src/openai_docs_scraper/ranking.py`
  - integrated ranking diagnostics into search results and API responses
  - blended lexical, vector, and structural signals in the search service
  - preserved a committed baseline report and split fresh runs into `latest_local.json`
  - improved page-vector MRR from `0.8456` to `0.8622` on the local benchmark while keeping exact-term and chunk retrieval strong
