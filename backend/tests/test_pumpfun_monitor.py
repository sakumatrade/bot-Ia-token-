from __future__ import annotations

from broker_sakuma.adapters.pumpfun.mock_provider import MockPumpFunProvider
from broker_sakuma.adapters.pumpfun.monitor import PumpFunMonitor
from broker_sakuma.adapters.pumpfun.provider import LaunchEvent
from broker_sakuma.config import RiskPolicyConfig
from broker_sakuma.db import models


def make_launch(**overrides) -> LaunchEvent:
    defaults = dict(
        mint_address="Mint111",
        symbol="DOGE2",
        name="Doge Two",
        creator_address="Creator111",
        initial_liquidity_usd=5000.0,
    )
    defaults.update(overrides)
    return LaunchEvent(**defaults)


def test_never_produces_buy_or_sell_only_watch_or_ignore(db_session):
    provider = MockPumpFunProvider([make_launch()])
    monitor = PumpFunMonitor(db_session, provider, RiskPolicyConfig())

    decisions = monitor.poll()
    assert len(decisions) == 1
    assert decisions[0].action in {"WATCH", "IGNORE"}


def test_low_liquidity_is_ignored(db_session):
    config = RiskPolicyConfig(min_liquidity_usd=1000.0)
    provider = MockPumpFunProvider([make_launch(initial_liquidity_usd=10.0)])
    monitor = PumpFunMonitor(db_session, provider, config)

    decision = monitor.poll()[0]
    assert decision.action == "IGNORE"
    assert "liquidity" in decision.reason


def test_healthy_launch_is_watched(db_session):
    config = RiskPolicyConfig(min_liquidity_usd=1000.0)
    provider = MockPumpFunProvider([make_launch(initial_liquidity_usd=5000.0)])
    monitor = PumpFunMonitor(db_session, provider, config)

    decision = monitor.poll()[0]
    assert decision.action == "WATCH"
    assert decision.risk_analysis.violated_rules == []


def test_flagged_creator_is_always_ignored_even_with_good_liquidity(db_session):
    creator = models.Creator(blockchain="solana", address="BadActor111", risk_notes="known rug puller")
    db_session.add(creator)
    db_session.commit()

    provider = MockPumpFunProvider([make_launch(creator_address="BadActor111", initial_liquidity_usd=100_000.0)])
    monitor = PumpFunMonitor(db_session, provider, RiskPolicyConfig(min_liquidity_usd=1000.0))

    decision = monitor.poll()[0]
    assert decision.action == "IGNORE"
    assert decision.creator_analysis.is_known_bad_actor is True


def test_registering_same_token_twice_does_not_duplicate(db_session):
    provider = MockPumpFunProvider([make_launch(), make_launch()])
    monitor = PumpFunMonitor(db_session, provider, RiskPolicyConfig(min_liquidity_usd=1000.0))
    monitor.poll()

    tokens = db_session.query(models.Token).filter_by(mint_address="Mint111").all()
    assert len(tokens) == 1


def test_high_launch_velocity_creator_gets_flagged_in_risk_analysis(db_session):
    monitor = PumpFunMonitor(db_session, MockPumpFunProvider(), RiskPolicyConfig(min_liquidity_usd=1000.0))
    for i in range(12):
        monitor.evaluate(make_launch(mint_address=f"Mint{i}", creator_address="Prolific111"))

    last = monitor.evaluate(make_launch(mint_address="MintLast", creator_address="Prolific111"))
    assert "creator_high_launch_velocity" in last.risk_analysis.violated_rules


def test_each_evaluation_records_an_opportunity(db_session):
    provider = MockPumpFunProvider([make_launch()])
    monitor = PumpFunMonitor(db_session, provider, RiskPolicyConfig(min_liquidity_usd=1000.0))
    monitor.poll()

    opportunities = db_session.query(models.Opportunity).filter_by(source="pumpfun_monitor").all()
    assert len(opportunities) == 1
    assert opportunities[0].evidence["category"] == "LAUNCHPAD"


def test_mock_provider_only_returns_pushed_launches_and_clears_after_poll(db_session):
    provider = MockPumpFunProvider()
    assert provider.fetch_new_launches() == []

    provider.push_launch(make_launch())
    launches = provider.fetch_new_launches()
    assert len(launches) == 1
    assert provider.fetch_new_launches() == []  # already consumed, like a real feed
