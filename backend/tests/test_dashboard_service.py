from __future__ import annotations

from datetime import datetime, timezone

import pytest

from broker_sakuma.core.enums import BotState, ThesisState, TradeSide
from broker_sakuma.db import models
from broker_sakuma.services.dashboard_service import build_dashboard_snapshot


def test_empty_system_reports_real_zeros_not_fake_data(db_session):
    snapshot = build_dashboard_snapshot(db_session)
    assert snapshot.capital_operational_usd == 0.0
    assert snapshot.active_bots == 0
    assert snapshot.dead_bots == 0
    assert snapshot.simulated_trades == 0
    assert snapshot.success_rate == 0.0


def test_snapshot_aggregates_bot_capital_and_pnl(db_session):
    b1 = models.Bot(name="Mother Bot", state=BotState.ACTIVE, capital_operational_usd=1000.0, cumulative_pnl_usd=50.0)
    b2 = models.Bot(name="Son 200", state=BotState.ACTIVE, capital_operational_usd=20.0, cumulative_pnl_usd=-5.0)
    b3 = models.Bot(name="Son 201", state=BotState.DEAD, capital_operational_usd=0.0, cumulative_pnl_usd=-5.0)
    db_session.add_all([b1, b2, b3])
    db_session.commit()

    snapshot = build_dashboard_snapshot(db_session)
    assert snapshot.capital_operational_usd == pytest.approx(1020.0)
    assert snapshot.total_pnl_usd == pytest.approx(40.0)
    assert snapshot.active_bots == 2
    assert snapshot.dead_bots == 1


def test_snapshot_counts_resurrections(db_session):
    bot = models.Bot(name="Son 210", state=BotState.DEAD)
    db_session.add(bot)
    db_session.commit()
    db_session.add(
        models.BotLineage(bot_id=bot.id, parent_id=bot.id, generation=1, relationship_type="resurrection")
    )
    db_session.commit()

    snapshot = build_dashboard_snapshot(db_session)
    assert snapshot.resurrected_bots == 1


def test_snapshot_buckets_theses_by_state(db_session):
    bot = models.Bot(name="Son 220", state=BotState.ACTIVE)
    db_session.add(bot)
    db_session.commit()

    db_session.add_all([
        models.Thesis(bot_id=bot.id, state=ThesisState.RESEARCH),
        models.Thesis(bot_id=bot.id, state=ThesisState.BACKTEST),
        models.Thesis(bot_id=bot.id, state=ThesisState.APPROVED),
    ])
    db_session.commit()

    snapshot = build_dashboard_snapshot(db_session)
    assert snapshot.new_theses == 1
    assert snapshot.approved_theses == 1
    assert snapshot.theses_in_research == 2  # RESEARCH + BACKTEST


def test_snapshot_computes_success_rate_ignoring_breakeven_trades(db_session):
    bot = models.Bot(name="Son 230", state=BotState.ACTIVE)
    db_session.add(bot)
    db_session.commit()

    now = datetime.now(timezone.utc)
    db_session.add_all([
        models.PaperTrade(bot_id=bot.id, side=TradeSide.SELL, price=1.0, quantity=1.0, simulated_pnl_usd=5.0, idempotency_key="t1", executed_at=now),
        models.PaperTrade(bot_id=bot.id, side=TradeSide.SELL, price=1.0, quantity=1.0, simulated_pnl_usd=-2.0, idempotency_key="t2", executed_at=now),
        models.PaperTrade(bot_id=bot.id, side=TradeSide.BUY, price=1.0, quantity=1.0, simulated_pnl_usd=0.0, idempotency_key="t3", executed_at=now),
    ])
    db_session.commit()

    snapshot = build_dashboard_snapshot(db_session)
    assert snapshot.simulated_trades == 3
    assert snapshot.success_rate == pytest.approx(0.5)  # 1 winner out of 2 decided trades
    assert snapshot.daily_pnl_usd == pytest.approx(3.0)


def test_snapshot_counts_unacknowledged_alerts_only(db_session):
    db_session.add_all([
        models.Alert(title="a", acknowledged=False),
        models.Alert(title="b", acknowledged=True),
    ])
    db_session.commit()

    snapshot = build_dashboard_snapshot(db_session)
    assert snapshot.unacknowledged_alerts == 1
