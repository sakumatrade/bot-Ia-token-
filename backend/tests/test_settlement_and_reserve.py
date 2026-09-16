from __future__ import annotations

from datetime import date

import pytest

from broker_sakuma.config import SettlementPolicyConfig, ThesisPolicyConfig
from broker_sakuma.core.enums import BotState
from broker_sakuma.db import models
from broker_sakuma.engines.daily_settlement_engine import AlreadySettledError, DailySettlementEngine
from broker_sakuma.engines.reserve_growth_engine import ReserveGrowthEngine
from broker_sakuma.engines.thesis_engine import ThesisEngine


@pytest.fixture()
def mother_and_son(db_session):
    mother = models.Bot(name="Mother Bot", generation=0, capital_operational_usd=1000.0, state=BotState.ACTIVE)
    db_session.add(mother)
    db_session.commit()
    son = models.Bot(name="Son 080", parent_id=mother.id, generation=1, capital_operational_usd=20.0, state=BotState.ACTIVE)
    db_session.add(son)
    db_session.commit()
    return mother, son


def test_profitable_day_splits_across_retain_reserve_and_mother(db_session, mother_and_son):
    mother, son = mother_and_son
    config = SettlementPolicyConfig(
        operational_capital_retention_pct=0.50,
        reserve_contribution_pct=0.20,
        returned_to_mother_pct=0.30,
    )
    engine = DailySettlementEngine(db_session, config, ReserveGrowthEngine(db_session))

    settlement = engine.settle(son, date(2026, 9, 16), gross_result_usd=10.0)

    assert settlement.retained_operational_usd == pytest.approx(5.0)
    assert settlement.reserve_contribution_usd == pytest.approx(2.0)
    assert settlement.returned_to_mother_usd == pytest.approx(3.0)

    db_session.refresh(son)
    db_session.refresh(mother)
    assert son.capital_operational_usd == pytest.approx(25.0)  # 20 + 5 retained
    assert son.reserve_usd == pytest.approx(2.0)
    assert mother.capital_operational_usd == pytest.approx(1003.0)


def test_losing_day_is_not_split_into_reserve_or_mother(db_session, mother_and_son):
    mother, son = mother_and_son
    config = SettlementPolicyConfig()
    engine = DailySettlementEngine(db_session, config, ReserveGrowthEngine(db_session))

    settlement = engine.settle(son, date(2026, 9, 16), gross_result_usd=-5.0)

    assert settlement.reserve_contribution_usd == 0.0
    assert settlement.returned_to_mother_usd == 0.0
    assert settlement.retained_operational_usd == pytest.approx(-5.0)

    db_session.refresh(son)
    assert son.capital_operational_usd == pytest.approx(15.0)  # 20 - 5
    assert son.reserve_usd == 0.0


def test_cannot_settle_same_bot_and_date_twice(db_session, mother_and_son):
    mother, son = mother_and_son
    engine = DailySettlementEngine(db_session, SettlementPolicyConfig(), ReserveGrowthEngine(db_session))
    engine.settle(son, date(2026, 9, 16), gross_result_usd=10.0)

    with pytest.raises(AlreadySettledError):
        engine.settle(son, date(2026, 9, 16), gross_result_usd=5.0)


def test_reserve_persists_across_days_and_new_thesis_still_starts_at_five_dollars(db_session, mother_and_son):
    """Spec section 55: the reserve survives day over day, but a new thesis
    never reads from it — it always starts at the configured $5."""

    mother, son = mother_and_son
    config = SettlementPolicyConfig(
        operational_capital_retention_pct=0.50, reserve_contribution_pct=0.30, returned_to_mother_pct=0.20
    )
    settlement_engine = DailySettlementEngine(db_session, config, ReserveGrowthEngine(db_session))

    settlement_engine.settle(son, date(2026, 9, 16), gross_result_usd=100.0)
    db_session.refresh(son)
    reserve_after_day_1 = son.reserve_usd
    assert reserve_after_day_1 == pytest.approx(30.0)

    settlement_engine.settle(son, date(2026, 9, 17), gross_result_usd=50.0)
    db_session.refresh(son)
    assert son.reserve_usd == pytest.approx(30.0 + 15.0)  # reserve accumulates, doesn't reset

    thesis_engine = ThesisEngine(db_session, ThesisPolicyConfig())
    thesis = thesis_engine.create_thesis(son)
    thesis_engine.advance_to_backtest(thesis)
    thesis_engine.advance_to_paper(thesis)
    thesis_engine.start_initial_test(thesis, son)

    assert thesis.current_capital_usd == 5.0  # unaffected by the now-large reserve


def test_reserve_growth_engine_rejects_negative_contribution(db_session):
    engine = ReserveGrowthEngine(db_session)
    with pytest.raises(ValueError):
        engine.contribute(bot_id=None, amount_usd=-1.0, reason="bad")


def test_mother_reserve_is_tracked_separately_from_bot_reserves(db_session, mother_and_son):
    mother, son = mother_and_son
    engine = ReserveGrowthEngine(db_session)

    engine.contribute(bot_id=son.id, amount_usd=10.0, reason="son reserve")
    engine.contribute(bot_id=None, amount_usd=500.0, reason="mother reserve")

    son_reserve = engine.get_or_create(son.id)
    mother_reserve = engine.get_or_create(None)

    assert son_reserve.balance_usd == pytest.approx(10.0)
    assert mother_reserve.balance_usd == pytest.approx(500.0)
