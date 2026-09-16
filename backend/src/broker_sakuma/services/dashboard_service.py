"""Aggregates the numbers the Dashboard (spec section 6) and the
`/api/dashboard` endpoint (spec section 38) show. Every field is computed
from real rows already written by the engines — nothing here invents a
number; an empty system legitimately reports zeros.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from broker_sakuma.core.enums import BotState, SystemState, ThesisState
from broker_sakuma.db import models
from broker_sakuma.engines.system_state import get_system_state

_DEAD_OR_DISABLED = {BotState.DEAD, BotState.DISABLED}
_RESEARCH_PIPELINE = {ThesisState.RESEARCH, ThesisState.BACKTEST, ThesisState.PAPER, ThesisState.INITIAL_TEST}


@dataclass
class DashboardSnapshot:
    system_state: SystemState
    capital_operational_usd: float
    reserve_usd: float
    capital_borrowed_usd: float
    daily_pnl_usd: float
    total_pnl_usd: float
    active_bots: int
    dead_bots: int
    resurrected_bots: int
    new_theses: int
    approved_theses: int
    theses_in_research: int
    simulated_trades: int
    success_rate: float
    max_drawdown_pct: float
    unacknowledged_alerts: int


def build_dashboard_snapshot(session: Session) -> DashboardSnapshot:
    system_state = get_system_state(session)
    bots = list(session.execute(select(models.Bot)).scalars())

    capital_operational_usd = sum(b.capital_operational_usd for b in bots)
    reserve_usd = sum(b.reserve_usd for b in bots)
    capital_borrowed_usd = sum(b.capital_borrowed_usd for b in bots)
    total_pnl_usd = sum(b.cumulative_pnl_usd for b in bots)
    active_bots = sum(1 for b in bots if BotState(b.state) not in _DEAD_OR_DISABLED)
    dead_bots = sum(1 for b in bots if BotState(b.state) == BotState.DEAD)
    max_drawdown_pct = max((b.drawdown_pct for b in bots), default=0.0)

    resurrected_bots = session.execute(
        select(models.BotLineage).where(models.BotLineage.relationship_type == "resurrection")
    ).scalars().all()

    theses = list(session.execute(select(models.Thesis)).scalars())
    new_theses = sum(1 for t in theses if ThesisState(t.state) == ThesisState.RESEARCH)
    approved_theses = sum(1 for t in theses if ThesisState(t.state) == ThesisState.APPROVED)
    theses_in_research = sum(1 for t in theses if ThesisState(t.state) in _RESEARCH_PIPELINE)

    paper_trades = list(session.execute(select(models.PaperTrade)).scalars())
    simulated_trades = len(paper_trades)
    decided_trades = [t for t in paper_trades if t.simulated_pnl_usd != 0]
    winning_trades = [t for t in decided_trades if t.simulated_pnl_usd > 0]
    success_rate = (len(winning_trades) / len(decided_trades)) if decided_trades else 0.0

    today = datetime.now(timezone.utc).date()
    daily_pnl_usd = sum(t.simulated_pnl_usd for t in paper_trades if t.executed_at.date() == today)

    unacknowledged_alerts = session.execute(
        select(models.Alert).where(models.Alert.acknowledged.is_(False))
    ).scalars().all()

    return DashboardSnapshot(
        system_state=system_state,
        capital_operational_usd=capital_operational_usd,
        reserve_usd=reserve_usd,
        capital_borrowed_usd=capital_borrowed_usd,
        daily_pnl_usd=daily_pnl_usd,
        total_pnl_usd=total_pnl_usd,
        active_bots=active_bots,
        dead_bots=dead_bots,
        resurrected_bots=len(resurrected_bots),
        new_theses=new_theses,
        approved_theses=approved_theses,
        theses_in_research=theses_in_research,
        simulated_trades=simulated_trades,
        success_rate=success_rate,
        max_drawdown_pct=max_drawdown_pct,
        unacknowledged_alerts=len(unacknowledged_alerts),
    )
