from __future__ import annotations

import pytest

from broker_sakuma.config import ThesisPolicyConfig
from broker_sakuma.core.enums import BotState, ThesisState
from broker_sakuma.db import models
from broker_sakuma.engines.thesis_engine import ThesisEngine, ThesisRuleViolation


@pytest.fixture()
def bot(db_session):
    b = models.Bot(name="Son 030", state=BotState.ACTIVE)
    db_session.add(b)
    db_session.commit()
    return b


def test_new_thesis_starts_at_research(db_session, bot):
    engine = ThesisEngine(db_session, ThesisPolicyConfig())
    thesis = engine.create_thesis(bot)
    assert thesis.state == ThesisState.RESEARCH
    assert thesis.current_capital_usd == 0.0


def test_initial_test_always_allocates_five_dollars_regardless_of_mother_wealth(db_session, bot):
    """The heart of spec section 10: even if the Mother Bot has millions,
    a brand-new thesis's initial test is always the configured $5."""

    mother_treasury = models.Treasury(owner="mother", total_capital_usd=5_000_000.0, available_to_loan_usd=1_000_000.0)
    db_session.add(mother_treasury)
    db_session.commit()

    engine = ThesisEngine(db_session, ThesisPolicyConfig())
    thesis = engine.create_thesis(bot)
    engine.advance_to_backtest(thesis)
    engine.advance_to_paper(thesis)
    engine.start_initial_test(thesis, bot)

    assert thesis.state == ThesisState.INITIAL_TEST
    assert thesis.current_capital_usd == 5.0

    funding = db_session.query(models.FundingEvent).filter_by(bot_id=bot.id).one()
    assert funding.amount_usd == 5.0
    assert funding.funding_type == "initial_thesis"


def test_dead_bot_cannot_start_new_thesis(db_session):
    dead_bot = models.Bot(name="Son 031", state=BotState.DEAD)
    db_session.add(dead_bot)
    db_session.commit()

    engine = ThesisEngine(db_session, ThesisPolicyConfig())
    with pytest.raises(ThesisRuleViolation):
        engine.create_thesis(dead_bot)


def test_cannot_skip_states(db_session, bot):
    engine = ThesisEngine(db_session, ThesisPolicyConfig())
    thesis = engine.create_thesis(bot)
    with pytest.raises(ThesisRuleViolation):
        engine.start_initial_test(thesis, bot)  # skipped BACKTEST/PAPER


def test_single_profitable_trade_is_not_enough_to_validate(db_session, bot):
    engine = ThesisEngine(db_session, ThesisPolicyConfig(min_operations_for_validation=20))
    thesis = engine.create_thesis(bot)
    engine.advance_to_backtest(thesis)
    engine.advance_to_paper(thesis)
    engine.start_initial_test(thesis, bot)

    advanced = engine.evaluate_for_validation(thesis, operations_count=1, drawdown_pct=0.0)
    assert advanced is False
    assert thesis.state == ThesisState.INITIAL_TEST


def test_validation_requires_low_drawdown_too(db_session, bot):
    engine = ThesisEngine(db_session, ThesisPolicyConfig(min_operations_for_validation=5, max_drawdown_pct_for_validation=0.10))
    thesis = engine.create_thesis(bot)
    engine.advance_to_backtest(thesis)
    engine.advance_to_paper(thesis)
    engine.start_initial_test(thesis, bot)

    advanced = engine.evaluate_for_validation(thesis, operations_count=10, drawdown_pct=0.50)
    assert advanced is False

    advanced = engine.evaluate_for_validation(thesis, operations_count=10, drawdown_pct=0.05)
    assert advanced is True
    assert thesis.state == ThesisState.VALIDATION


def test_escalation_is_one_rung_at_a_time(db_session, bot):
    ladder = [5.0, 10.0, 25.0, 50.0, 100.0]
    engine = ThesisEngine(db_session, ThesisPolicyConfig(escalation_ladder_usd=ladder))
    thesis = engine.create_thesis(bot)
    engine.advance_to_backtest(thesis)
    engine.advance_to_paper(thesis)
    engine.start_initial_test(thesis, bot)
    engine.evaluate_for_validation(thesis, operations_count=999, drawdown_pct=0.0)
    engine.approve(thesis)

    assert thesis.current_capital_usd == 5.0
    next_amount = engine.next_escalation_amount(thesis)
    assert next_amount == 10.0

    thesis.current_capital_usd = next_amount
    next_amount = engine.next_escalation_amount(thesis)
    assert next_amount == 25.0


def test_cannot_escalate_before_approval(db_session, bot):
    engine = ThesisEngine(db_session, ThesisPolicyConfig())
    thesis = engine.create_thesis(bot)
    with pytest.raises(ThesisRuleViolation):
        engine.next_escalation_amount(thesis)
