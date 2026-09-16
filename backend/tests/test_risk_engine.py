from __future__ import annotations

from broker_sakuma.config import RiskPolicyConfig
from broker_sakuma.core.enums import SystemState, TradeSide
from broker_sakuma.engines.risk_engine import OrderRequest, RiskEngine


def make_order(**overrides) -> OrderRequest:
    defaults = dict(
        bot_id="bot-1",
        side=TradeSide.BUY,
        price=1.0,
        quantity=5.0,
        liquidity_usd=5000.0,
        slippage_pct=0.01,
        wallet_balance_usd=100.0,
        daily_loss_so_far_usd=0.0,
        trades_today_count=0,
        consecutive_losses=0,
    )
    defaults.update(overrides)
    return OrderRequest(**defaults)


def test_approves_order_within_all_limits():
    engine = RiskEngine(RiskPolicyConfig())
    decision = engine.evaluate(make_order(), SystemState.ONLINE)
    assert decision.approved
    assert decision.violated_rules == []


def test_rejects_when_system_not_online():
    engine = RiskEngine(RiskPolicyConfig())
    for state in (SystemState.PAUSED, SystemState.SAFE_HALT, SystemState.EMERGENCY_STOP):
        decision = engine.evaluate(make_order(), state)
        assert not decision.approved
        assert any("system_state_not_online" in v for v in decision.violated_rules)


def test_rejects_position_above_max_position_usd():
    config = RiskPolicyConfig(max_position_usd=5.0)
    engine = RiskEngine(config)
    decision = engine.evaluate(make_order(price=10.0, quantity=1.0), SystemState.ONLINE)
    assert not decision.approved
    assert any("max_position_usd_exceeded" in v for v in decision.violated_rules)


def test_rejects_low_liquidity():
    config = RiskPolicyConfig(min_liquidity_usd=1000.0)
    engine = RiskEngine(config)
    decision = engine.evaluate(make_order(liquidity_usd=50.0), SystemState.ONLINE)
    assert not decision.approved
    assert any("min_liquidity_usd_violated" in v for v in decision.violated_rules)


def test_rejects_excess_slippage():
    config = RiskPolicyConfig(max_slippage_pct=0.02)
    engine = RiskEngine(config)
    decision = engine.evaluate(make_order(slippage_pct=0.10), SystemState.ONLINE)
    assert not decision.approved
    assert any("max_slippage_pct_exceeded" in v for v in decision.violated_rules)


def test_rejects_when_daily_loss_limit_reached():
    config = RiskPolicyConfig(max_daily_loss_usd=20.0)
    engine = RiskEngine(config)
    decision = engine.evaluate(make_order(daily_loss_so_far_usd=25.0), SystemState.ONLINE)
    assert not decision.approved
    assert any("max_daily_loss_usd_exceeded" in v for v in decision.violated_rules)


def test_rejects_when_max_trades_per_day_reached():
    config = RiskPolicyConfig(max_trades_per_day=3)
    engine = RiskEngine(config)
    decision = engine.evaluate(make_order(trades_today_count=3), SystemState.ONLINE)
    assert not decision.approved
    assert any("max_trades_per_day_exceeded" in v for v in decision.violated_rules)


def test_rejects_when_consecutive_losses_reached():
    config = RiskPolicyConfig(max_consecutive_losses=2)
    engine = RiskEngine(config)
    decision = engine.evaluate(make_order(consecutive_losses=2), SystemState.ONLINE)
    assert not decision.approved
    assert any("max_consecutive_losses_exceeded" in v for v in decision.violated_rules)


def test_rejects_below_min_wallet_balance():
    config = RiskPolicyConfig(min_wallet_balance_usd=5.0)
    engine = RiskEngine(config)
    decision = engine.evaluate(make_order(wallet_balance_usd=1.0), SystemState.ONLINE)
    assert not decision.approved
    assert any("min_wallet_balance_usd_violated" in v for v in decision.violated_rules)
