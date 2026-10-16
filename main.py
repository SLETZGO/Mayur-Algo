"""Vercel ASGI entrypoint for the FastAPI application."""

from __future__ import annotations

import sys
from pathlib import Path


# The project uses a src/ package layout. Make it importable when Vercel loads
# this root-level entrypoint directly from the repository checkout.
SRC_DIRECTORY = str(Path(__file__).resolve().parent / "src")
if SRC_DIRECTORY not in sys.path:
    sys.path.insert(0, SRC_DIRECTORY)

from nifty_algo.api.app import create_app

app = create_app()
