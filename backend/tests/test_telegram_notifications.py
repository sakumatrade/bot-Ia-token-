from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from broker_sakuma.adapters.telegram.bot_client import TelegramBotClient
from broker_sakuma.config import RiskPolicyConfig, TelegramConfig
from broker_sakuma.core.enums import BotState, TradeSide
from broker_sakuma.db import models
from broker_sakuma.engines.telegram_notifications import ProfitNotifier
from broker_sakuma.paper.paper_executor import PaperExecutor, PaperOrderRequest


def make_client_and_capture():
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    client = TelegramBotClient("FAKE_TOKEN", transport=httpx.MockTransport(handler))
    return client, captured


def test_not_configured_when_disabled(db_session):
    notifier = ProfitNotifier(TelegramConfig(enabled=False, bot_token="x", owner_user_id="1"))
    assert notifier.is_configured is False


def test_not_configured_without_token_or_owner(db_session):
    assert ProfitNotifier(TelegramConfig(enabled=True, bot_token=None, owner_user_id="1")).is_configured is False
    assert ProfitNotifier(TelegramConfig(enabled=True, bot_token="x", owner_user_id=None)).is_configured is False


def test_never_notifies_about_a_losing_or_flat_trade(db_session):
    client, captured = make_client_and_capture()
    notifier = ProfitNotifier(TelegramConfig(enabled=True, bot_token="x", owner_user_id="1"), client=client)

    bot = models.Bot(name="Son 920", cumulative_pnl_usd=-1.0)
    losing_trade = models.PaperTrade(
        bot_id="x", side=TradeSide.SELL, price=1.0, quantity=1.0, simulated_pnl_usd=-1.0,
        idempotency_key="t1", executed_at=datetime.now(timezone.utc),
    )
    sent = notifier.notify_profit(bot, losing_trade)
    assert sent is False
    assert captured == []


def test_notifies_on_a_profitable_trade(db_session):
    client, captured = make_client_and_capture()
    notifier = ProfitNotifier(TelegramConfig(enabled=True, bot_token="x", owner_user_id="777"), client=client)

    bot = models.Bot(name="Son 921", cumulative_pnl_usd=5.0)
    winning_trade = models.PaperTrade(
        bot_id="x", side=TradeSide.SELL, price=2.0, quantity=1.0, simulated_pnl_usd=5.0,
        idempotency_key="t2", executed_at=datetime.now(timezone.utc),
    )
    sent = notifier.notify_profit(bot, winning_trade)
    assert sent is True
    assert len(captured) == 1

    import json

    body = json.loads(captured[0].content)
    assert body["chat_id"] == "777"
    assert "Son 921" in body["text"]
    assert "5.00" in body["text"]


def test_paper_executor_calls_notifier_only_on_profitable_sell(db_session):
    client, captured = make_client_and_capture()
    notifier = ProfitNotifier(TelegramConfig(enabled=True, bot_token="x", owner_user_id="1"), client=client)

    bot = models.Bot(name="Son 922", state=BotState.ACTIVE, capital_operational_usd=50.0, peak_equity_usd=50.0)
    token = models.Token(mint_address="NotifyMint1", symbol="NTF")
    db_session.add_all([bot, token])
    db_session.commit()

    executor = PaperExecutor(db_session, RiskPolicyConfig(), notifier=notifier)

    buy = executor.execute(
        PaperOrderRequest(
            bot_id=bot.id, token_id=token.id, side=TradeSide.BUY, reference_price=1.0, quantity=5.0,
            liquidity_usd=5000.0, slippage_pct=0.0, fee_pct=0.0,
        ),
        idempotency_key="notify-buy-1",
    )
    assert buy.approved
    assert captured == []  # a BUY has no realized P&L; must never notify

    sell = executor.execute(
        PaperOrderRequest(
            bot_id=bot.id, token_id=token.id, side=TradeSide.SELL, reference_price=2.0, quantity=5.0,
            liquidity_usd=5000.0, slippage_pct=0.0, fee_pct=0.0,
        ),
        idempotency_key="notify-sell-1",
    )
    assert sell.approved
    assert len(captured) == 1


def test_paper_executor_without_notifier_still_works(db_session):
    """Backward compatible: passing no notifier at all must not break anything."""

    bot = models.Bot(name="Son 923", state=BotState.ACTIVE, capital_operational_usd=50.0, peak_equity_usd=50.0)
    token = models.Token(mint_address="NoNotifyMint1", symbol="NN")
    db_session.add_all([bot, token])
    db_session.commit()

    executor = PaperExecutor(db_session, RiskPolicyConfig())
    result = executor.execute(
        PaperOrderRequest(
            bot_id=bot.id, token_id=token.id, side=TradeSide.BUY, reference_price=1.0, quantity=5.0,
            liquidity_usd=5000.0, slippage_pct=0.0, fee_pct=0.0,
        ),
        idempotency_key="no-notifier-1",
    )
    assert result.approved
