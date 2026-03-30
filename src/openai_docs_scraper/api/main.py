"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..services.config import get_settings
from .routes import docs, ingest, process, project, scrape, search


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="OpenAI Docs Scraper API",
    description="REST API for scraping, ingesting, summarizing, embedding, and searching OpenAI documentation.",
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
    return {
        "db_path": str(s.db_path.expanduser().resolve()),
        "md_export_root": str(s.md_export_root.expanduser().resolve()),
        "raw_dir": str(s.raw_dir.expanduser().resolve()),
        "embedding_model": s.embedding_model,
        "summary_model": s.summary_model,
    }


@app.get("/health")
async def health_check():
    """Health check with paths from settings (database / export may be mounted volumes)."""
    s = get_settings()
    db = s.db_path.expanduser().resolve()
    export = s.md_export_root.expanduser().resolve()
    return {
        "status": "healthy",
        "db_path": str(db),
        "db_exists": db.is_file(),
        "md_export_root": str(export),
        "index_md_exists": (export / "index.md").is_file(),
    }
