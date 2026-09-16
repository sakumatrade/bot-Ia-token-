from __future__ import annotations

import pytest

from broker_sakuma.config import RiskPolicyConfig
from broker_sakuma.core.enums import BotState, PositionStatus, SystemState, TradeSide
from broker_sakuma.db import models
from broker_sakuma.engines.system_state import KillSwitch
from broker_sakuma.paper.paper_executor import InsufficientPositionError, PaperExecutor, PaperOrderRequest


@pytest.fixture()
def bot_and_token(db_session):
    bot = models.Bot(
        name="Son 020",
        state=BotState.ACTIVE,
        capital_operational_usd=50.0,
        peak_equity_usd=50.0,
        max_loss_usd=5.0,
    )
    token = models.Token(mint_address="MintAAA", symbol="AAA")
    db_session.add_all([bot, token])
    db_session.commit()
    return bot, token


def test_buy_then_profitable_sell_updates_balance_and_pnl(db_session, bot_and_token):
    bot, token = bot_and_token
    executor = PaperExecutor(db_session, RiskPolicyConfig())

    buy = executor.execute(
        PaperOrderRequest(
            bot_id=bot.id,
            token_id=token.id,
            side=TradeSide.BUY,
            reference_price=1.0,
            quantity=5.0,
            liquidity_usd=5000.0,
            slippage_pct=0.0,
            fee_pct=0.0,
        ),
        idempotency_key="buy-1",
    )
    assert buy.approved
    assert buy.trade.price == 1.0
    db_session.refresh(bot)
    assert bot.capital_operational_usd == 45.0  # 50 - 5*1.0

    sell = executor.execute(
        PaperOrderRequest(
            bot_id=bot.id,
            token_id=token.id,
            side=TradeSide.SELL,
            reference_price=2.0,
            quantity=5.0,
            liquidity_usd=5000.0,
            slippage_pct=0.0,
            fee_pct=0.0,
        ),
        idempotency_key="sell-1",
    )
    assert sell.approved
    assert sell.trade.simulated_pnl_usd == pytest.approx(5.0)  # (2.0-1.0)*5
    db_session.refresh(bot)
    assert bot.capital_operational_usd == 55.0  # 45 + 5*2.0
    assert bot.cumulative_pnl_usd == pytest.approx(5.0)

    position = db_session.query(models.Position).filter_by(bot_id=bot.id, token_id=token.id).one()
    assert position.status == PositionStatus.CLOSED


def test_selling_more_than_held_raises(db_session, bot_and_token):
    bot, token = bot_and_token
    executor = PaperExecutor(db_session, RiskPolicyConfig())

    with pytest.raises(InsufficientPositionError):
        executor.execute(
            PaperOrderRequest(
                bot_id=bot.id,
                token_id=token.id,
                side=TradeSide.SELL,
                reference_price=1.0,
                quantity=5.0,
                liquidity_usd=5000.0,
                slippage_pct=0.0,
            ),
            idempotency_key="bad-sell-1",
        )


def test_duplicate_idempotency_key_does_not_double_execute(db_session, bot_and_token):
    bot, token = bot_and_token
    executor = PaperExecutor(db_session, RiskPolicyConfig())

    order = PaperOrderRequest(
        bot_id=bot.id,
        token_id=token.id,
        side=TradeSide.BUY,
        reference_price=1.0,
        quantity=5.0,
        liquidity_usd=5000.0,
        slippage_pct=0.0,
        fee_pct=0.0,
    )
    first = executor.execute(order, idempotency_key="idem-dup")
    second = executor.execute(order, idempotency_key="idem-dup")

    assert first.approved and not first.duplicate
    assert second.approved and second.duplicate
    assert second.trade.id == first.trade.id

    db_session.refresh(bot)
    assert bot.capital_operational_usd == 45.0  # only debited once


def test_kill_switch_blocks_new_orders(db_session, bot_and_token):
    bot, token = bot_and_token
    KillSwitch(db_session).engage(reason="test halt", actor="owner")

    executor = PaperExecutor(db_session, RiskPolicyConfig())
    result = executor.execute(
        PaperOrderRequest(
            bot_id=bot.id,
            token_id=token.id,
            side=TradeSide.BUY,
            reference_price=1.0,
            quantity=5.0,
            liquidity_usd=5000.0,
            slippage_pct=0.0,
        ),
        idempotency_key="blocked-1",
    )
    assert not result.approved
    assert "system_state_not_online" in result.reason


def test_dead_bot_cannot_trade(db_session, bot_and_token):
    bot, token = bot_and_token
    bot.state = BotState.DEAD
    db_session.add(bot)
    db_session.commit()

    executor = PaperExecutor(db_session, RiskPolicyConfig())
    result = executor.execute(
        PaperOrderRequest(
            bot_id=bot.id,
            token_id=token.id,
            side=TradeSide.BUY,
            reference_price=1.0,
            quantity=5.0,
            liquidity_usd=5000.0,
            slippage_pct=0.0,
        ),
        idempotency_key="dead-bot-1",
    )
    assert not result.approved
    assert result.reason == "bot_is_dead"


def test_bot_dies_after_repeated_losing_trades(db_session, bot_and_token):
    """Spec section 54: a bot that loses down to its configured ceiling must
    become DEAD, mid-session, without needing an external process."""

    bot, token = bot_and_token
    executor = PaperExecutor(db_session, RiskPolicyConfig())

    for i in range(4):
        buy = executor.execute(
            PaperOrderRequest(
                bot_id=bot.id,
                token_id=token.id,
                side=TradeSide.BUY,
                reference_price=1.0,
                quantity=5.0,
                liquidity_usd=5000.0,
                slippage_pct=0.0,
                fee_pct=0.01,
            ),
            idempotency_key=f"buy-loss-{i}",
        )
        if not buy.approved:
            break

        sell = executor.execute(
            PaperOrderRequest(
                bot_id=bot.id,
                token_id=token.id,
                side=TradeSide.SELL,
                reference_price=0.5,
                quantity=5.0,
                liquidity_usd=5000.0,
                slippage_pct=0.0,
                fee_pct=0.01,
            ),
            idempotency_key=f"sell-loss-{i}",
        )
        if sell.bot_died:
            break

    db_session.refresh(bot)
    assert bot.state == BotState.DEAD
    assert bot.cumulative_pnl_usd <= -5.0
    assert bot.died_at is not None

    post_mortem_ready_events = (
        db_session.query(models.BotLifecycleEvent).filter_by(bot_id=bot.id, to_state=BotState.DEAD.value).all()
    )
    assert len(post_mortem_ready_events) == 1
