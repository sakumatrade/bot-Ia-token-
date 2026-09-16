"""FastAPI application factory for the Broker Sakuma Local API."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from broker_sakuma.adapters.pumpfun.mock_provider import MockPumpFunProvider
from broker_sakuma.adapters.pumpfun.synthetic_launch_generator import SyntheticLaunchGenerator
from broker_sakuma.api.routes import bots as bots_routes
from broker_sakuma.api.routes import dashboard as dashboard_routes
from broker_sakuma.api.routes import misc as misc_routes
from broker_sakuma.api.routes import system as system_routes
from broker_sakuma.api.routes import web as web_routes
from broker_sakuma.config import Settings
from broker_sakuma.db.base import Base, make_engine, make_session_factory
from broker_sakuma.engines.autonomous_trading_cycle import AutonomousTradingCycle
from broker_sakuma.engines.telegram_notifications import ProfitNotifier

logger = logging.getLogger(__name__)


async def _auto_trading_loop(app: FastAPI) -> None:
    """Background tick for the autonomous PAPER-trading loop (spec
    sections 3, 22, 28) — only runs when an operator explicitly sets
    ``auto_trading.enabled=True``; disabled by default. Never touches
    real money: every trade still goes through the same ``PaperExecutor``
    every other phase uses, against synthetic mock launches only.
    """

    settings: Settings = app.state.settings
    while True:
        await asyncio.sleep(settings.auto_trading.interval_seconds)
        try:
            session = app.state.session_factory()
            try:
                provider = MockPumpFunProvider()
                generator = SyntheticLaunchGenerator()
                for _ in range(max(1, settings.auto_trading.launches_per_cycle)):
                    provider.push_launch(generator.generate())
                notifier = ProfitNotifier(settings.telegram) if settings.telegram.enabled else None
                cycle = AutonomousTradingCycle(session, provider, settings.risk, settings.auto_trading, notifier=notifier)
                cycle.run_once()
            finally:
                session.close()
        except asyncio.CancelledError:
            raise
        except Exception:  # a bad cycle must never take the whole server down
            logger.exception("autonomous trading cycle failed; will retry next tick")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    task: asyncio.Task | None = None
    if app.state.settings.auto_trading.enabled:
        task = asyncio.create_task(_auto_trading_loop(app))
    try:
        yield
    finally:
        if task is not None:
            task.cancel()


def create_app(settings: Settings | None = None, create_tables: bool = True) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Broker Sakuma Local API", version="0.1.0", lifespan=_lifespan)

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
    app.include_router(web_routes.router)

    return app
