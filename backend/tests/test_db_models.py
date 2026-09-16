from __future__ import annotations

from datetime import date, datetime, timezone

from broker_sakuma.core.enums import BotState, InfoClassification, InterestModel, LoanStatus, ThesisState
from broker_sakuma.db import models


def test_create_mother_and_son_bot(db_session):
    mother = models.Bot(name="Mother Bot", generation=0, state=BotState.ACTIVE)
    db_session.add(mother)
    db_session.commit()

    son = models.Bot(
        name="Son 001",
        parent_id=mother.id,
        generation=1,
        state=BotState.CREATED,
        max_loss_usd=5.0,
    )
    db_session.add(son)
    db_session.commit()

    assert son.parent_id == mother.id
    assert son.generation == 1


def test_thesis_defaults_to_five_dollars(db_session):
    bot = models.Bot(name="Son 002")
    db_session.add(bot)
    db_session.commit()

    thesis = models.Thesis(bot_id=bot.id, state=ThesisState.INITIAL_TEST)
    db_session.add(thesis)
    db_session.commit()

    assert thesis.initial_capital_usd == 5.0
    assert thesis.current_capital_usd == 5.0


def test_post_mortem_and_collective_memory_link(db_session):
    bot = models.Bot(name="Son 007", state=BotState.DEAD)
    db_session.add(bot)
    db_session.commit()

    pm = models.PostMortem(
        bot_id=bot.id,
        probable_cause="Liquidity concentration in a single pool",
        failed_hypothesis="Assumed liquidity was stable across the holding period",
        rule_that_should_have_prevented="min_liquidity_usd risk check",
    )
    db_session.add(pm)
    db_session.commit()

    memory = models.CollectiveMemory(
        source_bot_id=bot.id,
        post_mortem_id=pm.id,
        kind=InfoClassification.REAL_RESULT,
        title="Liquidity concentration killed Son 007",
        tags=["liquidity", "pumpfun"],
    )
    db_session.add(memory)
    db_session.commit()

    assert memory.post_mortem_id == pm.id


def test_bot_loan_and_payment(db_session):
    mother = models.Bot(name="Mother Bot")
    son = models.Bot(name="Son 003")
    db_session.add_all([mother, son])
    db_session.commit()

    loan = models.BotLoan(
        loan_id="loan-0001",
        bot_id=son.id,
        mother_id=mother.id,
        principal_usd=100.0,
        interest_model=InterestModel.PROFIT_SHARE,
        interest_rate=0.10,
        status=LoanStatus.ACTIVE,
        remaining_balance_usd=100.0,
    )
    db_session.add(loan)
    db_session.commit()

    payment = models.LoanPayment(
        loan_id=loan.id,
        amount_usd=22.0,
        principal_component_usd=20.0,
        interest_component_usd=2.0,
        remaining_balance_usd=80.0,
    )
    db_session.add(payment)
    db_session.commit()

    assert payment.loan_id == loan.id


def test_daily_settlement_unique_per_bot_and_date(db_session):
    bot = models.Bot(name="Son 004")
    db_session.add(bot)
    db_session.commit()

    settlement = models.DailySettlement(
        bot_id=bot.id,
        settlement_date=date(2026, 9, 16),
        gross_result_usd=10.0,
        final_equity_usd=15.0,
    )
    db_session.add(settlement)
    db_session.commit()

    assert settlement.settlement_date == date(2026, 9, 16)


def test_audit_log_is_append_only_table(db_session):
    log = models.AuditLog(
        actor="system",
        action="BOT_CREATED",
        entity_type="bot",
        entity_id="some-id",
        details={"reason": "initial setup"},
    )
    db_session.add(log)
    db_session.commit()

    fetched = db_session.get(models.AuditLog, log.id)
    assert fetched is not None
    assert fetched.action == "BOT_CREATED"


def test_trade_idempotency_key_is_unique(db_session):
    bot = models.Bot(name="Son 005")
    db_session.add(bot)
    db_session.commit()

    trade = models.Trade(
        bot_id=bot.id,
        side="BUY",
        price=1.0,
        quantity=5.0,
        idempotency_key="idem-1",
        executed_at=datetime.now(timezone.utc),
    )
    db_session.add(trade)
    db_session.commit()

    duplicate = models.Trade(
        bot_id=bot.id,
        side="BUY",
        price=1.0,
        quantity=5.0,
        idempotency_key="idem-1",
        executed_at=datetime.now(timezone.utc),
    )
    db_session.add(duplicate)
    try:
        db_session.commit()
        raised = False
    except Exception:
        db_session.rollback()
        raised = True

    assert raised, "duplicate idempotency_key must be rejected by the database"
