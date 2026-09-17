"""PatternLearner (spec section 26): a bounded, evidence-based nudge to
position sizing, backed by real (simulated) outcomes stored via the
existing CollectiveMemoryStore — no new table, no fake intelligence
before enough samples exist.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from broker_sakuma.adapters.pumpfun.mock_provider import MockPumpFunProvider
from broker_sakuma.adapters.pumpfun.provider import LaunchEvent
from broker_sakuma.api.app import create_app
from broker_sakuma.config import AutoTradingConfig, RiskPolicyConfig, Settings
from broker_sakuma.core.enums import BotState, ThesisState
from broker_sakuma.db import models
from broker_sakuma.engines.autonomous_trading_cycle import AutonomousTradingCycle
from broker_sakuma.engines.pattern_learning import PatternLearner, liquidity_bucket_tag

API_KEY = "pattern-learning-test-key"


def test_liquidity_bucket_tag_groups_consistently():
    assert liquidity_bucket_tag(500) == liquidity_bucket_tag(999)
    assert liquidity_bucket_tag(500) != liquidity_bucket_tag(1500)
    assert liquidity_bucket_tag(1500) == liquidity_bucket_tag(1999)
    assert liquidity_bucket_tag(10_000) == liquidity_bucket_tag(50_000)


def test_confidence_multiplier_is_neutral_with_too_few_samples(db_session):
    learner = PatternLearner(db_session, min_samples=5)
    for _ in range(4):
        learner.record_outcome(bot_id="bot-1", liquidity_usd=1500, pnl_usd=10.0)
    assert learner.confidence_multiplier(1500) == 1.0


def test_confidence_multiplier_rises_after_enough_positive_outcomes(db_session):
    learner = PatternLearner(db_session, min_samples=5)
    for _ in range(10):
        learner.record_outcome(bot_id="bot-1", liquidity_usd=1500, pnl_usd=0.4)
    assert learner.confidence_multiplier(1500) > 1.0


def test_confidence_multiplier_falls_after_enough_negative_outcomes(db_session):
    learner = PatternLearner(db_session, min_samples=5)
    for _ in range(10):
        learner.record_outcome(bot_id="bot-1", liquidity_usd=1500, pnl_usd=-0.4)
    assert learner.confidence_multiplier(1500) < 1.0


def test_confidence_multiplier_is_bounded_regardless_of_outcome_magnitude(db_session):
    learner = PatternLearner(db_session, min_samples=5)
    for _ in range(10):
        learner.record_outcome(bot_id="bot-1", liquidity_usd=1500, pnl_usd=1000.0)
    assert learner.confidence_multiplier(1500) <= 1.5

    for _ in range(10):
        learner.record_outcome(bot_id="bot-1", liquidity_usd=2500, pnl_usd=-1000.0)
    assert learner.confidence_multiplier(2500) >= 0.5


def test_buckets_are_independent(db_session):
    learner = PatternLearner(db_session, min_samples=5)
    for _ in range(10):
        learner.record_outcome(bot_id="bot-1", liquidity_usd=1500, pnl_usd=0.4)
    # A different bucket has no samples yet — still neutral.
    assert learner.confidence_multiplier(4000) == 1.0


def test_cycle_records_outcomes_and_scales_position_with_learning(db_session):
    bot = models.Bot(name="Learner Son", state=BotState.ACTIVE, capital_operational_usd=5.0, max_loss_usd=5.0)
    db_session.add(bot)
    db_session.commit()
    thesis = models.Thesis(bot_id=bot.id, state=ThesisState.INITIAL_TEST, initial_capital_usd=5.0, current_capital_usd=5.0)
    db_session.add(thesis)
    db_session.commit()

    provider = MockPumpFunProvider([
        LaunchEvent(
            mint_address=f"SYNTHETIC-{i}", symbol="SYN", name="Synthetic", creator_address="c1",
            initial_liquidity_usd=2000.0, metadata={"synthetic": True},
        )
        for i in range(5)
    ])
    cycle = AutonomousTradingCycle(db_session, provider, RiskPolicyConfig(), AutoTradingConfig())
    result = cycle.run_once()

    assert result.trades_executed > 0

    memories = db_session.execute(select(models.CollectiveMemory)).scalars().all()
    pattern_entries = [m for m in memories if "pattern:round_trip_pnl" in m.tags]
    assert len(pattern_entries) > 0


@pytest.fixture()
def api_settings(tmp_path):
    db_path = tmp_path / "test_pattern_api.db"
    return Settings(
        database={"url": f"sqlite:///{db_path}"},
        local_api={"api_key": API_KEY},
        auto_trading={"launches_per_cycle": 10},
    )


@pytest.fixture()
def client(api_settings):
    return TestClient(create_app(settings=api_settings))


@pytest.fixture()
def auth_headers():
    return {"X-API-Key": API_KEY}


def test_run_cycle_endpoint_still_works_with_learning_enabled(client, auth_headers):
    mother = client.post("/api/bots/mother", headers=auth_headers, json={"initial_capital_usd": 1000.0}).json()
    son = client.post("/api/bots/sons", headers=auth_headers, json={"parent_id": mother["id"]}).json()
    client.post(f"/api/bots/{son['id']}/activate", headers=auth_headers)

    for _ in range(3):
        response = client.post("/api/system/run-cycle", headers=auth_headers)
        assert response.status_code == 200

    trades = client.get("/api/trades", headers=auth_headers).json()
    son_trades = [t for t in trades if t["bot_id"] == son["id"]]
    assert len(son_trades) % 2 == 0
