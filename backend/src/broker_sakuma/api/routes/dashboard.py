from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from broker_sakuma.api.deps import get_db, get_settings, require_api_key
from broker_sakuma.api.schemas import DashboardResponse, StatusResponse
from broker_sakuma.config import Settings
from broker_sakuma.engines.system_state import get_system_state
from broker_sakuma.services.dashboard_service import build_dashboard_snapshot

router = APIRouter(tags=["dashboard"], dependencies=[Depends(require_api_key)])


@router.get("/status", response_model=StatusResponse)
def get_status(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> StatusResponse:
    state = get_system_state(db)
    return StatusResponse(
        system_state=state.value,
        environment=settings.environment.value,
        live_trading_enabled=settings.trading.live_trading_enabled,
    )


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(db: Session = Depends(get_db)) -> DashboardResponse:
    snapshot = build_dashboard_snapshot(db)
    return DashboardResponse(
        system_state=snapshot.system_state.value,
        capital_operational_usd=snapshot.capital_operational_usd,
        reserve_usd=snapshot.reserve_usd,
        capital_borrowed_usd=snapshot.capital_borrowed_usd,
        daily_pnl_usd=snapshot.daily_pnl_usd,
        total_pnl_usd=snapshot.total_pnl_usd,
        active_bots=snapshot.active_bots,
        dead_bots=snapshot.dead_bots,
        resurrected_bots=snapshot.resurrected_bots,
        new_theses=snapshot.new_theses,
        approved_theses=snapshot.approved_theses,
        theses_in_research=snapshot.theses_in_research,
        simulated_trades=snapshot.simulated_trades,
        success_rate=snapshot.success_rate,
        max_drawdown_pct=snapshot.max_drawdown_pct,
        unacknowledged_alerts=snapshot.unacknowledged_alerts,
    )
