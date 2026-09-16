"""FastAPI application factory for the Broker Sakuma Local API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from broker_sakuma.api.routes import bots as bots_routes
from broker_sakuma.api.routes import dashboard as dashboard_routes
from broker_sakuma.api.routes import misc as misc_routes
from broker_sakuma.api.routes import system as system_routes
from broker_sakuma.config import Settings
from broker_sakuma.db.base import Base, make_engine, make_session_factory


def create_app(settings: Settings | None = None, create_tables: bool = True) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Broker Sakuma Local API", version="0.1.0")

    engine = make_engine(settings.database.url, echo=settings.database.echo)
    if create_tables:
        Base.metadata.create_all(engine)

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)

    # Origin validation for browser-based callers (spec section 38:
    # "Validar origem"). The native macOS app is not a browser and is
    # unaffected by CORS; this specifically guards a future Safari
    # extension / any web-based caller.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.local_api.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["X-API-Key", "Content-Type"],
    )

    app.include_router(dashboard_routes.router, prefix="/api")
    app.include_router(bots_routes.router, prefix="/api")
    app.include_router(misc_routes.router, prefix="/api")
    app.include_router(system_routes.router, prefix="/api")

    return app
