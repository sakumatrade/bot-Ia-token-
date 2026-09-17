"""Shared FastAPI dependencies: DB session and authentication.

Authentication is a single shared-secret API key checked in constant time
(spec section 38: "Adicionar autenticação"). There is no cookie-based
session here, so classic CSRF (which relies on browsers automatically
attaching ambient cookie credentials) does not apply to this transport —
that is a deliberate design choice, not an oversight, and is why no CSRF
token machinery is implemented. Origin validation for browser-based
callers (e.g. a future Safari extension) is handled separately via
CORSMiddleware in ``app.py``.
"""

from __future__ import annotations

import secrets
from collections.abc import Generator

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from broker_sakuma.config import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    settings: Settings = Depends(get_settings),
) -> str:
    """Accepts either the main (read-write) key or the optional read-only
    key (spec: a free, view-only link for people watching the bot learn,
    with no deposit and no way to change anything — see
    ``read_only_api_key``'s own docstring). The read-only key is only ever
    valid on a GET request; any state-changing request with it is
    rejected the same as a missing key, never silently downgraded to a
    no-op, so a route can never be mistakenly left writable for viewers
    just because it forgot to check.
    """

    configured_key = settings.local_api.api_key
    read_only_key = settings.local_api.read_only_api_key

    if configured_key and x_api_key and secrets.compare_digest(x_api_key, configured_key):
        return x_api_key

    if read_only_key and x_api_key and secrets.compare_digest(x_api_key, read_only_key):
        if request.method != "GET":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="read-only API key cannot perform this action",
            )
        return x_api_key

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing API key")
