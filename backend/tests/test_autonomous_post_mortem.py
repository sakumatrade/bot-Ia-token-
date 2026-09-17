"""A bot that dies inside the autonomous PAPER-trading loop has no human
watching to write up why by hand — spec section 13 says a bot's history
must never be silently discarded, so AutonomousTradingCycle must create
a PostMortem itself when this happens (engines/autonomous_trading_cycle.py).
"""

from __future__ import annotations

from sqlalchemy import select

from broker_sakuma.adapters.pumpfun.mock_provider import MockPumpFunProvider
from broker_sakuma.adapters.pumpfun.provider import LaunchEvent
from broker_sakuma.config import AutoTradingConfig, RiskPolicyConfig
from broker_sakuma.core.enums import BotState, ThesisState
from broker_sakuma.db import models
from broker_sakuma.engines.autonomous_trading_cycle import AutonomousTradingCycle


def test_bot_dying_in_the_loop_gets_an_automatic_post_mortem(db_session):
    # capital_operational_usd stays high on purpose, so the RiskEngine's
    # min_wallet_balance_usd floor never blocks a BUY before cumulative_pnl
    # (a separate, all-time-realized field) actually reaches the max-loss
    # ceiling - otherwise the bot just gets locked out of trading instead
    # of dying, which is a different (and separately correct) outcome.
    # A fixed id keeps the outcome deterministic: the synthetic exit-price
    # walk is seeded by f"{mint_address}:{bot_id}", so a random bot.id
    # would make this test's win/loss outcome vary run to run.
    bot = models.Bot(
        id="doomed-son-fixed-test-id", name="Doomed Son", state=BotState.ACTIVE, capital_operational_usd=1000.0,
        max_loss_usd=5.0, cumulative_pnl_usd=-4.99,
    )
    db_session.add(bot)
    db_session.commit()
    thesis = models.Thesis(bot_id=bot.id, state=ThesisState.INITIAL_TEST, initial_capital_usd=5.0, current_capital_usd=5.0)
    db_session.add(thesis)
    db_session.commit()

    # Enough independent synthetic launches that at least one produces a
    # losing round trip (each has a real, if imperfect, chance of one
    # given the liquidity-biased-but-still-randomized price walk) -
    # any loss of one cent or more breaches the ceiling from here.
    launches = [
        LaunchEvent(
            mint_address=f"SYNTHETIC-lossmaker-{i}", symbol="SYN", name="Synthetic", creator_address="c1",
            initial_liquidity_usd=1000.0, metadata={"synthetic": True},
        )
        for i in range(30)
    ]
    provider = MockPumpFunProvider(launches)
    cycle = AutonomousTradingCycle(db_session, provider, RiskPolicyConfig(), AutoTradingConfig())
    result = cycle.run_once()

    assert bot.id in result.bots_died
    db_session.refresh(bot)
    assert bot.state == BotState.DEAD

    post_mortems = db_session.execute(select(models.PostMortem).where(models.PostMortem.bot_id == bot.id)).scalars().all()
    assert len(post_mortems) == 1
    pm = post_mortems[0]
    assert pm.thesis_id == thesis.id
    assert pm.probable_cause
    assert "max-loss" in pm.probable_cause or "max_loss" in pm.probable_cause


def test_a_bot_that_survives_gets_no_post_mortem(db_session):
    bot = models.Bot(name="Survivor Son", state=BotState.ACTIVE, capital_operational_usd=1000.0, max_loss_usd=5.0)
    db_session.add(bot)
    db_session.commit()
    thesis = models.Thesis(bot_id=bot.id, state=ThesisState.INITIAL_TEST, initial_capital_usd=5.0, current_capital_usd=5.0)
    db_session.add(thesis)
    db_session.commit()

    provider = MockPumpFunProvider([LaunchEvent(
        mint_address="SYNTHETIC-fine", symbol="SYN", name="Synthetic", creator_address="c1",
        initial_liquidity_usd=2000.0, metadata={"synthetic": True},
    )])
    cycle = AutonomousTradingCycle(db_session, provider, RiskPolicyConfig(), AutoTradingConfig())
    cycle.run_once()

    db_session.refresh(bot)
    assert bot.state != BotState.DEAD
    post_mortems = db_session.execute(select(models.PostMortem).where(models.PostMortem.bot_id == bot.id)).scalars().all()
    assert post_mortems == []
