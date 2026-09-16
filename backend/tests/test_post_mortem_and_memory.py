from __future__ import annotations

import pytest

from broker_sakuma.core.enums import BotState, InfoClassification
from broker_sakuma.db import models
from broker_sakuma.engines.collective_memory import CollectiveMemoryStore
from broker_sakuma.engines.post_mortem_engine import BotPostMortemEngine


@pytest.fixture()
def dead_bot(db_session):
    bot = models.Bot(name="Son 040", state=BotState.DEAD, cumulative_pnl_usd=-5.0, max_loss_usd=5.0)
    db_session.add(bot)
    db_session.commit()
    return bot


def test_post_mortem_requires_dead_bot(db_session):
    alive_bot = models.Bot(name="Son 041", state=BotState.ACTIVE)
    db_session.add(alive_bot)
    db_session.commit()

    engine = BotPostMortemEngine(db_session)
    with pytest.raises(ValueError):
        engine.create_post_mortem(alive_bot, probable_cause="n/a")


def test_post_mortem_captures_full_context(db_session, dead_bot):
    engine = BotPostMortemEngine(db_session)
    pm = engine.create_post_mortem(
        dead_bot,
        probable_cause="Liquidity concentration in a single pool",
        entry_price=1.0,
        exit_price=0.5,
        slippage_pct=0.03,
        liquidity_usd=800.0,
        market_condition="thin order book, single LP",
        failed_hypothesis="assumed liquidity would remain stable",
        rule_that_should_have_prevented="min_liquidity_usd risk check",
    )

    assert pm.bot_id == dead_bot.id
    assert pm.confirmed_cause is None

    events = db_session.query(models.BotLifecycleEvent).filter_by(bot_id=dead_bot.id).all()
    assert any(e.event_type == "POST_MORTEM_CREATED" for e in events)


def test_confirm_cause_updates_in_place_never_deletes(db_session, dead_bot):
    engine = BotPostMortemEngine(db_session)
    pm = engine.create_post_mortem(dead_bot, probable_cause="Liquidity concentration")
    original_id = pm.id

    engine.confirm_cause(pm, confirmed_cause="Confirmed: single LP pulled liquidity")

    assert pm.id == original_id
    assert pm.probable_cause == "Liquidity concentration"
    assert pm.confirmed_cause == "Confirmed: single LP pulled liquidity"

    still_there = db_session.get(models.PostMortem, original_id)
    assert still_there is not None


def test_collective_memory_records_and_finds_by_tag(db_session, dead_bot):
    pm_engine = BotPostMortemEngine(db_session)
    pm = pm_engine.create_post_mortem(dead_bot, probable_cause="Liquidity concentration")

    memory = CollectiveMemoryStore(db_session)
    memory.record_from_post_mortem(pm, dead_bot, title="Son 040 died", tags=["liquidity", "pumpfun"])
    memory.record(
        source_bot_id=dead_bot.id,
        kind=InfoClassification.HYPOTHESIS,
        title="Unrelated hypothesis",
        tags=["unrelated"],
    )

    found = memory.find_by_tags(["liquidity"])
    assert len(found) == 1
    assert found[0].title == "Son 040 died"

    not_found = memory.find_by_tags(["nonexistent_tag"])
    assert not_found == []
