from __future__ import annotations

import pytest

from broker_sakuma.config import GrowthPolicyConfig, MaximumLossPolicyConfig, ThesisPolicyConfig
from broker_sakuma.core.enums import BotState, ThesisState
from broker_sakuma.db import models
from broker_sakuma.engines.collective_memory import CollectiveMemoryStore
from broker_sakuma.engines.lineage_engine import LineageEngine
from broker_sakuma.engines.max_loss_policy import MaximumLossPolicy
from broker_sakuma.engines.post_mortem_engine import BotPostMortemEngine
from broker_sakuma.engines.resurrection_engine import BotResurrectionEngine, ResurrectionError
from broker_sakuma.engines.thesis_engine import ThesisEngine


@pytest.fixture()
def rig(db_session):
    lineage = LineageEngine(db_session, GrowthPolicyConfig(), MaximumLossPolicyConfig())
    memory = CollectiveMemoryStore(db_session)
    resurrection = BotResurrectionEngine(db_session, lineage, memory)
    post_mortem = BotPostMortemEngine(db_session)
    return dict(lineage=lineage, memory=memory, resurrection=resurrection, post_mortem=post_mortem)


def test_cannot_resurrect_a_living_bot(db_session, rig):
    bot = models.Bot(name="Son 050", state=BotState.ACTIVE)
    db_session.add(bot)
    db_session.commit()

    fake_pm = models.PostMortem(bot_id=bot.id, probable_cause="n/a")
    db_session.add(fake_pm)
    db_session.commit()

    with pytest.raises(ResurrectionError):
        rig["resurrection"].resurrect(bot, fake_pm, correction="n/a")


def test_full_death_to_resurrection_cycle_starts_new_thesis_at_five_dollars(db_session, rig):
    """Spec section 54, end to end: $5 thesis -> loss -> DEAD -> post-mortem
    -> collective memory -> Son-R1 -> new thesis also starts at $5."""

    mother = rig["lineage"].create_mother_bot(initial_capital_usd=10_000.0)
    son = rig["lineage"].spawn_son(mother, name="Son 017")

    thesis_engine = ThesisEngine(db_session, ThesisPolicyConfig())
    thesis = thesis_engine.create_thesis(son)
    thesis_engine.advance_to_backtest(thesis)
    thesis_engine.advance_to_paper(thesis)
    thesis_engine.start_initial_test(thesis, son)
    assert son.capital_operational_usd == 0.0  # funding event recorded capital, wallet crediting is a treasury concern

    son.max_loss_usd = 5.0
    son.cumulative_pnl_usd = -5.0  # simulate the thesis losing all $5
    db_session.add(son)
    db_session.commit()

    died = MaximumLossPolicy().enforce(db_session, son, reason="thesis lost the full $5 stake")
    assert died is True
    assert son.state == BotState.DEAD

    pm = rig["post_mortem"].create_post_mortem(
        son,
        thesis_id=thesis.id,
        probable_cause="Liquidity concentration in a single pool",
        failed_hypothesis="assumed liquidity was stable",
        rule_that_should_have_prevented="min_liquidity_usd risk check",
    )

    new_bot = rig["resurrection"].resurrect(
        son,
        pm,
        correction="Add a liquidity concentration filter before entry",
    )

    assert new_bot.name == "Son 017-R1"
    assert new_bot.parent_id == son.id
    assert new_bot.state == BotState.CREATED
    assert new_bot.capital_operational_usd == 0.0

    lineage_row = db_session.query(models.BotLineage).filter_by(bot_id=new_bot.id).one()
    assert lineage_row.relationship_type == "resurrection"
    assert lineage_row.previous_failure == "Liquidity concentration in a single pool"
    assert lineage_row.correction == "Add a liquidity concentration filter before entry"

    # The new bot's own first thesis must still start at exactly $5 —
    # resurrection never grants it a head start.
    new_thesis = thesis_engine.create_thesis(new_bot)
    thesis_engine.advance_to_backtest(new_thesis)
    thesis_engine.advance_to_paper(new_thesis)
    thesis_engine.start_initial_test(new_thesis, new_bot)
    assert new_thesis.current_capital_usd == 5.0

    # The failure must be discoverable in collective memory by future bots.
    found = rig["memory"].find_by_tags(["post_mortem"])
    assert any("Son 017 died" in entry.title for entry in found)


def test_resurrecting_twice_increments_version_suffix(db_session, rig):
    mother = rig["lineage"].create_mother_bot()
    son = rig["lineage"].spawn_son(mother, name="Son 060")
    son.state = BotState.DEAD
    db_session.add(son)
    db_session.commit()

    pm1 = rig["post_mortem"].create_post_mortem(son, probable_cause="cause 1")
    r1 = rig["resurrection"].resurrect(son, pm1, correction="fix 1")
    assert r1.name == "Son 060-R1"

    r1.state = BotState.DEAD
    db_session.add(r1)
    db_session.commit()
    pm2 = models.PostMortem(bot_id=r1.id, probable_cause="cause 2")
    db_session.add(pm2)
    db_session.commit()

    # resurrect again FROM r1 (its own dead version), which is a fresh
    # resurrection lineage rooted at r1, not son.
    r2 = rig["resurrection"].resurrect(r1, pm2, correction="fix 2")
    assert r2.name == "Son 060-R1-R1"
    assert r2.parent_id == r1.id
