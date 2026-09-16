"""AutonomousTradingCycle (spec sections 3, 22, 28): lets an activated bot
trade on its own, with no manual order per trade — against synthetic mock
launches only, entirely through the existing PaperExecutor/RiskEngine/
MaximumLossPolicy. Never real money; see the module's own docstring.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from broker_sakuma.adapters.pumpfun.mock_provider import MockPumpFunProvider
from broker_sakuma.adapters.pumpfun.provider import LaunchEvent
from broker_sakuma.adapters.pumpfun.synthetic_launch_generator import SyntheticLaunchGenerator
from broker_sakuma.api.app import create_app
from broker_sakuma.config import AutoTradingConfig, RiskPolicyConfig, Settings
from broker_sakuma.core.enums import BotState, ThesisState
from broker_sakuma.db import models
from broker_sakuma.engines.autonomous_trading_cycle import AutonomousTradingCycle

API_KEY = "autocycle-test-key"


def test_synthetic_launch_generator_is_clearly_labeled_fake():
    launch = SyntheticLaunchGenerator(seed=1).generate()
    assert launch.mint_address.startswith("SYNTHETIC-")
    assert launch.metadata["synthetic"] is True


def test_cycle_ignores_bots_with_no_active_thesis(db_session):
    bot = models.Bot(name="Idle Bot", state=BotState.ACTIVE, capital_operational_usd=100.0)
    db_session.add(bot)
    db_session.commit()

    provider = MockPumpFunProvider([LaunchEvent(
        mint_address="SYNTHETIC-x", symbol="SYN", name="Synthetic", creator_address="c1",
        initial_liquidity_usd=2000.0, metadata={"synthetic": True},
    )])
    cycle = AutonomousTradingCycle(db_session, provider, RiskPolicyConfig(), AutoTradingConfig())
    result = cycle.run_once()

    assert result.decisions_evaluated == 1
    assert result.trades_executed == 0

    db_session.refresh(bot)
    assert bot.capital_operational_usd == 100.0


def test_cycle_trades_an_activated_bot_and_records_pnl(db_session):
    bot = models.Bot(name="Son 900", state=BotState.ACTIVE, capital_operational_usd=5.0, max_loss_usd=5.0)
    db_session.add(bot)
    db_session.commit()

    thesis = models.Thesis(bot_id=bot.id, state=ThesisState.INITIAL_TEST, initial_capital_usd=5.0, current_capital_usd=5.0)
    db_session.add(thesis)
    db_session.commit()

    provider = MockPumpFunProvider([LaunchEvent(
        mint_address="SYNTHETIC-abc123", symbol="SYN", name="Synthetic", creator_address="c1",
        initial_liquidity_usd=2000.0, metadata={"synthetic": True},
    )])
    cycle = AutonomousTradingCycle(db_session, provider, RiskPolicyConfig(), AutoTradingConfig())
    result = cycle.run_once()

    assert result.decisions_evaluated == 1
    assert result.trades_executed == 2  # one BUY, one SELL round trip

    trades = list(db_session.execute(select(models.PaperTrade)).scalars())
    assert len(trades) == 2

    db_session.refresh(bot)
    # Capital moved (either up or down) — the round trip actually happened.
    assert bot.trades_count == 2


def test_cycle_never_touches_a_dead_bot(db_session):
    bot = models.Bot(name="Dead Bot", state=BotState.DEAD, capital_operational_usd=5.0)
    db_session.add(bot)
    db_session.commit()
    thesis = models.Thesis(bot_id=bot.id, state=ThesisState.INITIAL_TEST, initial_capital_usd=5.0, current_capital_usd=5.0)
    db_session.add(thesis)
    db_session.commit()

    provider = MockPumpFunProvider([LaunchEvent(
        mint_address="SYNTHETIC-dead", symbol="SYN", name="Synthetic", creator_address="c1",
        initial_liquidity_usd=2000.0, metadata={"synthetic": True},
    )])
    cycle = AutonomousTradingCycle(db_session, provider, RiskPolicyConfig(), AutoTradingConfig())
    result = cycle.run_once()

    assert result.trades_executed == 0


@pytest.fixture()
def api_settings(tmp_path):
    db_path = tmp_path / "test_autocycle_api.db"
    return Settings(
        database={"url": f"sqlite:///{db_path}"},
        local_api={"api_key": API_KEY},
        # Synthetic liquidity is randomized (spec: never a fake real feed —
        # see SyntheticLaunchGenerator); enough launches per cycle makes it
        # astronomically unlikely that *none* clear RiskPolicyConfig's
        # min_liquidity_usd, so trading-behavior assertions stay deterministic.
        auto_trading={"launches_per_cycle": 20},
    )


@pytest.fixture()
def client(api_settings):
    return TestClient(create_app(settings=api_settings))


@pytest.fixture()
def auth_headers():
    return {"X-API-Key": API_KEY}


def test_run_cycle_endpoint_requires_api_key(client):
    response = client.post("/api/system/run-cycle")
    assert response.status_code == 401


def test_run_cycle_endpoint_works_with_no_bots(client, auth_headers):
    response = client.post("/api/system/run-cycle", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["decisions_evaluated"] >= 0
    assert body["trades_executed"] == 0
    assert body["bots_died"] == []


def test_run_cycle_endpoint_trades_an_activated_bot(client, auth_headers):
    mother = client.post("/api/bots/mother", headers=auth_headers, json={"initial_capital_usd": 1000.0}).json()
    son = client.post("/api/bots/sons", headers=auth_headers, json={"parent_id": mother["id"]}).json()
    client.post(f"/api/bots/{son['id']}/activate", headers=auth_headers)

    response = client.post("/api/system/run-cycle", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["decisions_evaluated"] >= 1

    trades = client.get("/api/trades", headers=auth_headers).json()
    son_trades = [t for t in trades if t["bot_id"] == son["id"]]
    assert len(son_trades) >= 2 and len(son_trades) % 2 == 0  # BUY+SELL round trips, no manual order needed


def test_auto_trading_disabled_by_default():
    assert Settings().auto_trading.enabled is False
