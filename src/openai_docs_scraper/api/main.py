"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..services.config import get_settings
from ..services.state import collect_artifact_state
from .routes import docs, ingest, process, project, scrape, search


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="LLM Provider Docs Ledger API",
    description="REST API for scraping, ingesting, summarizing, embedding, and searching provider documentation snapshots.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(project.router, prefix="/project", tags=["Project"])
app.include_router(scrape.router, prefix="/scrape", tags=["Scrape"])
app.include_router(ingest.router, prefix="/ingest", tags=["Ingest"])
app.include_router(process.router, prefix="/process", tags=["Process"])
app.include_router(search.router, prefix="/search", tags=["Search"])
app.include_router(docs.router, prefix="/docs", tags=["Docs"])


@app.get("/config")
async def app_config():
    """Resolved defaults for data paths and models (no secrets)."""
    s = get_settings()
    state = collect_artifact_state(s)
    return {
        "source_name": s.source_name,
        "available_sources": state.available_sources,
        "sitemap_url": s.sitemap_url,
        "sitemap_path": str(s.sitemap_path.expanduser().resolve()),
        "db_path": str(s.db_path.expanduser().resolve()),
        "md_export_root": str(s.md_export_root.expanduser().resolve()),
        "raw_dir": str(s.raw_dir.expanduser().resolve()),
        "embedding_model": s.embedding_model,
        "summary_model": s.summary_model,
        "answer_model": s.answer_model,
        "refresh_discovery_interval_minutes": s.refresh_discovery_interval_minutes,
        "refresh_targeted_interval_hours": s.refresh_targeted_interval_hours,
        "refresh_reconcile_interval_hours": s.refresh_reconcile_interval_hours,
        "refresh_integrity_interval_days": s.refresh_integrity_interval_days,
        "refresh_lock_dir": str(s.refresh_lock_dir.expanduser().resolve()),
        "refresh_lock_timeout_s": s.refresh_lock_timeout_s,
        "refresh_log_path": str(s.refresh_log_path.expanduser().resolve()),
        "latest_run_id": state.latest_run_id,
        "latest_run_status": state.latest_run_status,
        "latest_successful_run_id": state.latest_successful_run_id,
        "active_snapshot_id": state.active_snapshot_id,
        "active_snapshot_published_at": state.active_snapshot_published_at,
    }


@app.get("/health")
async def health_check():
    """Health check with paths from settings (database / export may be mounted volumes)."""
    s = get_settings()
    state = collect_artifact_state(s)
    status = "healthy"
    if not state.db_exists or not state.raw_dir_exists:
        status = "degraded"
    return {
        "status": status,
        **state.as_dict(),
    }
