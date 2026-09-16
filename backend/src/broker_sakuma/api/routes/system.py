from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from broker_sakuma.adapters.pumpfun.mock_provider import MockPumpFunProvider
from broker_sakuma.adapters.pumpfun.synthetic_launch_generator import SyntheticLaunchGenerator
from broker_sakuma.api.deps import get_db, get_settings, require_api_key
from broker_sakuma.api.schemas import KillSwitchRequest, RunCycleResponse, SystemActionResponse
from broker_sakuma.config import Settings
from broker_sakuma.engines.autonomous_trading_cycle import AutonomousTradingCycle
from broker_sakuma.engines.telegram_notifications import ProfitNotifier
from broker_sakuma.services.system_control_service import SystemControlService, SystemTransitionError

router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(require_api_key)])


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
