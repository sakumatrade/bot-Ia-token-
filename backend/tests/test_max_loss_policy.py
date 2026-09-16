from __future__ import annotations

from broker_sakuma.core.enums import BotState
from broker_sakuma.db import models
from broker_sakuma.engines.max_loss_policy import MaximumLossPolicy


def test_bot_under_limit_survives(db_session):
    bot = models.Bot(name="Son 010", max_loss_usd=5.0, cumulative_pnl_usd=-3.0, state=BotState.ACTIVE)
    db_session.add(bot)
    db_session.commit()

    policy = MaximumLossPolicy()
    died = policy.enforce(db_session, bot, reason="check")

    assert died is False
    assert bot.state == BotState.ACTIVE


def test_bot_breaching_limit_dies(db_session):
    bot = models.Bot(name="Son 011", max_loss_usd=5.0, cumulative_pnl_usd=-5.0, state=BotState.ACTIVE)
    db_session.add(bot)
    db_session.commit()

    policy = MaximumLossPolicy()
    died = policy.enforce(db_session, bot, reason="loss ceiling reached")

    assert died is True
    assert bot.state == BotState.DEAD
    assert bot.died_at is not None

    events = db_session.query(models.BotLifecycleEvent).filter_by(bot_id=bot.id).all()
    assert any(e.to_state == BotState.DEAD.value for e in events)

    risk_events = db_session.query(models.RiskEvent).filter_by(bot_id=bot.id).all()
    assert any(e.event_type == "MAX_LOSS_BREACHED" for e in risk_events)


def test_already_dead_bot_is_left_alone(db_session):
    bot = models.Bot(name="Son 012", max_loss_usd=5.0, cumulative_pnl_usd=-50.0, state=BotState.DEAD)
    db_session.add(bot)
    db_session.commit()

    policy = MaximumLossPolicy()
    died = policy.enforce(db_session, bot, reason="already dead")

    assert died is False
