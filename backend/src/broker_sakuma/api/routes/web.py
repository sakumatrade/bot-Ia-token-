"""Serves the browser-based dashboard (backend/src/broker_sakuma/web/static/index.html).

Added as a pragmatic, cross-platform complement to the macOS app and
Safari extension: the backend is plain Python and already runs on any
OS, so this page lets someone see live status/P&L/bots/alerts from any
browser, on any machine, without needing Xcode or a Mac at all — the
macOS app remains the "real" native experience the spec asks for, this
is a fallback that works today.

Deliberately NOT behind `require_api_key`: this route only ever serves
static markup with no data in it. The page's own JavaScript then calls
the authenticated `/api/*` endpoints directly from the browser, holding
the API key in that browser's `localStorage` — the exact same pattern
the Safari extension already uses.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse

router = APIRouter(tags=["web"])

_STATIC_DIR = Path(__file__).resolve().parents[2] / "web" / "static"
_INDEX_FILE = _STATIC_DIR / "index.html"


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard")


@router.get("/dashboard", include_in_schema=False)
def dashboard_page() -> FileResponse:
    return FileResponse(_INDEX_FILE, media_type="text/html")
