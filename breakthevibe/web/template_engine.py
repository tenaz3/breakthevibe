"""Shared Jinja2Templates singleton for all route modules."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
