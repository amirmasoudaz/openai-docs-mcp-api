from __future__ import annotations

import os

from dotenv import load_dotenv

# Repo-root `.env` is picked up when running scripts from the project directory.
load_dotenv()


def require_openai_api_key() -> None:
    if os.getenv("OPENAI_API_KEY"):
        return
    raise RuntimeError(
        "OPENAI_API_KEY is not set. Export it in your shell or create a `.env` file."
    )

