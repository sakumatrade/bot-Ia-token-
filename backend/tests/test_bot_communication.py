from __future__ import annotations

import pytest

from broker_sakuma.core.enums import BotState, InfoClassification
from broker_sakuma.db import models
from broker_sakuma.engines.bot_communication import BotCommunicationEngine, BotCouncil, CouncilOpinion


@pytest.fixture()
def bots(db_session):
    a = models.Bot(name="Son 100", state=BotState.ACTIVE)
    b = models.Bot(name="Son 101", state=BotState.ACTIVE)
    c = models.Bot(name="Son 102", state=BotState.ACTIVE)
    db_session.add_all([a, b, c])
    db_session.commit()
    return a, b, c


def test_broadcast_requires_a_title(db_session):
    engine = BotCommunicationEngine(db_session)
    with pytest.raises(ValueError):
        engine.broadcast(None, InfoClassification.FACT, title="   ")


def test_broadcast_preserves_classification(db_session, bots):
    a, _, _ = bots
    engine = BotCommunicationEngine(db_session)

    fact = engine.broadcast(a.id, InfoClassification.FACT, "Creator X launched 5 tokens this week")
    hypothesis = engine.broadcast(a.id, InfoClassification.HYPOTHESIS, "Creator X's tokens tend to rug within 24h")

    assert fact.kind == InfoClassification.FACT
    assert hypothesis.kind == InfoClassification.HYPOTHESIS


def test_feed_since_filters_by_kind(db_session, bots):
    a, _, _ = bots
    engine = BotCommunicationEngine(db_session)
    engine.broadcast(a.id, InfoClassification.FACT, "fact 1")
    engine.broadcast(a.id, InfoClassification.HYPOTHESIS, "hypothesis 1")
    engine.broadcast(a.id, InfoClassification.SIMULATION, "sim 1")

    facts_only = engine.feed_since(kinds=[InfoClassification.FACT])
    assert len(facts_only) == 1
    assert facts_only[0].title == "fact 1"


def test_verified_ground_truth_excludes_hypotheses_and_opinions(db_session, bots):
    a, _, _ = bots
    engine = BotCommunicationEngine(db_session)
    engine.broadcast(a.id, InfoClassification.FACT, "fact 1")
    engine.broadcast(a.id, InfoClassification.REAL_RESULT, "real result 1")
    engine.broadcast(a.id, InfoClassification.HYPOTHESIS, "hypothesis 1")
    engine.broadcast(a.id, InfoClassification.AGENT_OPINION, "opinion 1")
    engine.broadcast(a.id, InfoClassification.SIMULATION, "sim 1")

    truth = engine.verified_ground_truth()
    titles = {e.title for e in truth}
    assert titles == {"fact 1", "real result 1"}


def test_council_cannot_convene_with_no_opinions(db_session):
    engine = BotCommunicationEngine(db_session)
    council = BotCouncil(db_session, engine)
    with pytest.raises(ValueError):
        council.convene([])


def test_council_majority_and_tally(db_session, bots):
    a, b, c = bots
    engine = BotCommunicationEngine(db_session)
    council = BotCouncil(db_session, engine)

    opinions = [
        CouncilOpinion(bot_id=a.id, verdict="BUY", confidence=0.8, reasoning="strong liquidity"),
        CouncilOpinion(bot_id=b.id, verdict="BUY", confidence=0.6, reasoning="creator has good history"),
        CouncilOpinion(bot_id=c.id, verdict="IGNORE", confidence=0.4, reasoning="thin order book"),
    ]

    verdict = council.convene(opinions, topic_bot_id=a.id)
    assert verdict.majority == "BUY"
    assert verdict.tally == {"BUY": 2, "IGNORE": 1}
    assert len(verdict.opinions) == 3


def test_council_verdict_is_recorded_as_agent_opinion_never_fact(db_session, bots):
    """Spec section 9: never treat a hypothesis (or a council vote) as a
    fact, no matter how many bots agree."""

    a, b, _ = bots
    engine = BotCommunicationEngine(db_session)
    council = BotCouncil(db_session, engine)

    opinions = [
        CouncilOpinion(bot_id=a.id, verdict="BUY", confidence=0.9, reasoning="x"),
        CouncilOpinion(bot_id=b.id, verdict="BUY", confidence=0.9, reasoning="y"),
    ]
    council.convene(opinions, topic_bot_id=a.id)

    recorded = db_session.query(models.LearningEvent).filter_by(title="Bot Council verdict: BUY").one()
    assert recorded.kind == InfoClassification.AGENT_OPINION

    ground_truth_titles = {e.title for e in engine.verified_ground_truth()}
    assert "Bot Council verdict: BUY" not in ground_truth_titles
