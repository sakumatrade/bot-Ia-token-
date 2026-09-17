from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from broker_sakuma.adapters.pumpfun.mock_provider import MockPumpFunProvider
from broker_sakuma.adapters.pumpfun.synthetic_launch_generator import SyntheticLaunchGenerator
from broker_sakuma.api.deps import get_db, get_settings, require_api_key
from broker_sakuma.api.schemas import (
    AutoTradingStatusResponse,
    KillSwitchRequest,
    RunCycleResponse,
    SystemActionResponse,
    UpdateAutoTradingRequest,
)
from broker_sakuma.config import Settings
from broker_sakuma.engines.autonomous_trading_cycle import AutonomousTradingCycle
from broker_sakuma.engines.telegram_notifications import ProfitNotifier
from broker_sakuma.services.system_control_service import SystemControlService, SystemTransitionError

router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(require_api_key)])


@router.get("/whoami")
def whoami(
    api_key: str = Depends(require_api_key),
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    """Lets the dashboard tell whether it's talking with the read-only
    viewer key (see ``config.py::LocalAPIConfig.read_only_api_key``) so it
    can hide every button that changes state, before a viewer ever tries
    one and hits the 403 the backend already enforces regardless."""

    read_only_key = settings.local_api.read_only_api_key
    is_read_only = bool(read_only_key) and api_key == read_only_key
    return {"read_only": is_read_only}


@router.post("/start", response_model=SystemActionResponse)
def start_system(db: Session = Depends(get_db)) -> SystemActionResponse:
    try:
        state = SystemControlService(db).start(actor="local_api")
    except SystemTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return SystemActionResponse(system_state=state.value)


@router.post("/pause", response_model=SystemActionResponse)
def pause_system(db: Session = Depends(get_db)) -> SystemActionResponse:
    try:
        state = SystemControlService(db).pause(actor="local_api")
    except SystemTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return SystemActionResponse(system_state=state.value)


@router.post("/resume", response_model=SystemActionResponse)
def resume_system(db: Session = Depends(get_db)) -> SystemActionResponse:
    try:
        state = SystemControlService(db).resume(actor="local_api")
    except SystemTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return SystemActionResponse(system_state=state.value)


@router.post("/kill-switch", response_model=SystemActionResponse)
def kill_switch(payload: KillSwitchRequest, db: Session = Depends(get_db)) -> SystemActionResponse:
    """Sensitive operation: requires an explicit, non-empty reason in the
    request body (spec section 38: "Operações sensíveis exigem autorização
    adicional"). Reachable from any state, and idempotent if already
    engaged — pressing it twice is safe, not a duplicate alert.
    """

    if not payload.reason.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="reason is required")

    state = SystemControlService(db).engage_kill_switch(actor="local_api", reason=payload.reason)
    return SystemActionResponse(system_state=state.value)


@router.post("/run-cycle", response_model=RunCycleResponse)
def run_cycle(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> RunCycleResponse:
    """Run one tick of the autonomous PAPER-trading loop manually — the
    same cycle the background scheduler runs automatically when
    ``auto_trading.enabled`` is set (see app.py). Simulated capital only,
    against synthetic mock launches; see
    ``engines/autonomous_trading_cycle.py`` for why that's safe.
    """

    provider = MockPumpFunProvider()
    generator = SyntheticLaunchGenerator()
    for _ in range(max(1, settings.auto_trading.launches_per_cycle)):
        provider.push_launch(generator.generate())

    notifier = ProfitNotifier(settings.telegram) if settings.telegram.enabled else None
    cycle = AutonomousTradingCycle(db, provider, settings.risk, settings.auto_trading, notifier=notifier)
    result = cycle.run_once()

    return RunCycleResponse(
        decisions_evaluated=result.decisions_evaluated,
        trades_executed=result.trades_executed,
        bots_died=result.bots_died,
    )


def _auto_trading_status(request: Request, settings: Settings) -> AutoTradingStatusResponse:
    task = getattr(request.app.state, "auto_trading_task", None)
    return AutoTradingStatusResponse(
        enabled=settings.auto_trading.enabled,
        running=task is not None and not task.done(),
        interval_seconds=settings.auto_trading.interval_seconds,
        launches_per_cycle=settings.auto_trading.launches_per_cycle,
        position_fraction_of_capital=settings.auto_trading.position_fraction_of_capital,
    )


@router.get("/auto-trading", response_model=AutoTradingStatusResponse)
def get_auto_trading(request: Request, settings: Settings = Depends(get_settings)) -> AutoTradingStatusResponse:
    return _auto_trading_status(request, settings)


@router.post("/auto-trading", response_model=AutoTradingStatusResponse)
async def update_auto_trading(
    payload: UpdateAutoTradingRequest, request: Request, settings: Settings = Depends(get_settings)
) -> AutoTradingStatusResponse:
    """Toggle or reconfigure the autonomous PAPER-trading loop live, with
    no server restart needed — a bot's operation stays simulated
    regardless (see ``engines/autonomous_trading_cycle.py``)."""

    from broker_sakuma.api.app import start_auto_trading, stop_auto_trading

    if payload.interval_seconds is not None:
        settings.auto_trading.interval_seconds = payload.interval_seconds
    if payload.launches_per_cycle is not None:
        settings.auto_trading.launches_per_cycle = payload.launches_per_cycle
    if payload.position_fraction_of_capital is not None:
        settings.auto_trading.position_fraction_of_capital = payload.position_fraction_of_capital

    if payload.enabled is not None:
        settings.auto_trading.enabled = payload.enabled

    if settings.auto_trading.enabled:
        # Restart so a changed interval/config takes effect immediately.
        stop_auto_trading(request.app)
        start_auto_trading(request.app)
    else:
        stop_auto_trading(request.app)

    return _auto_trading_status(request, settings)
