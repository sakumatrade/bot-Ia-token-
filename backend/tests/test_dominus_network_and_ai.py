"""Dominus Network (GET /api/learning-events) and Dominus AI
(GET /api/pattern-insights): both surface data that already existed
internally — bot broadcasts/council verdicts (BotCommunicationEngine,
spec section 9) and PatternLearner's accumulated outcomes (spec section
26) — read-only, no new behavior.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from broker_sakuma.api.app import create_app
from broker_sakuma.config import Settings
from broker_sakuma.core.enums import InfoClassification
from broker_sakuma.engines.bot_communication import BotCommunicationEngine, CouncilOpinion, BotCouncil
from broker_sakuma.engines.pattern_learning import PatternLearner, all_bucket_tags, liquidity_bucket_tag

API_KEY = "dominus-network-ai-test-key"


def test_all_bucket_tags_matches_liquidity_bucket_tag():
    tags = all_bucket_tags()
    assert len(tags) == 5
    assert len(set(tags)) == 5  # every bucket is distinct
    assert tags[0] == liquidity_bucket_tag(500.0)
    assert tags[-1] == liquidity_bucket_tag(6000.0)


def test_bucket_insights_empty_with_no_outcomes(db_session):
    learner = PatternLearner(db_session, min_samples=5)
    assert learner.bucket_insights() == []


def test_bucket_insights_includes_only_buckets_with_data(db_session):
    learner = PatternLearner(db_session, min_samples=5)
    for _ in range(3):
        learner.record_outcome(bot_id="bot-1", liquidity_usd=1500, pnl_usd=0.4)

    insights = learner.bucket_insights()
    assert len(insights) == 1
    assert insights[0]["liquidity_bucket_tag"] == liquidity_bucket_tag(1500)
    assert insights[0]["samples_count"] == 3
    assert insights[0]["average_pnl_usd"] == pytest.approx(0.4)
    # Below min_samples - neutral multiplier, but still reported (evidence
    # accumulating is itself worth showing, just not yet "confident").
    assert insights[0]["confidence_multiplier"] == 1.0


def test_bucket_insights_multiplier_matches_confidence_multiplier(db_session):
    learner = PatternLearner(db_session, min_samples=5)
    for _ in range(6):
        learner.record_outcome(bot_id="bot-1", liquidity_usd=1500, pnl_usd=0.3)

    insights = learner.bucket_insights()
    assert insights[0]["confidence_multiplier"] == learner.confidence_multiplier(1500)
    assert insights[0]["confidence_multiplier"] > 1.0


@pytest.fixture()
def api_settings(tmp_path):
    db_path = tmp_path / "test_dominus_network_ai_api.db"
    return Settings(database={"url": f"sqlite:///{db_path}"}, local_api={"api_key": API_KEY})


@pytest.fixture()
def client(api_settings):
    return TestClient(create_app(settings=api_settings))


@pytest.fixture()
def auth_headers():
    return {"X-API-Key": API_KEY}


def test_learning_events_requires_api_key(client):
    assert client.get("/api/learning-events").status_code == 401


def test_pattern_insights_requires_api_key(client):
    assert client.get("/api/pattern-insights").status_code == 401


def test_learning_events_empty_by_default(client, auth_headers):
    response = client.get("/api/learning-events", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_pattern_insights_empty_by_default(client, auth_headers):
    response = client.get("/api/pattern-insights", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_learning_events_surfaces_bot_council_verdict(db_session, client, auth_headers):
    comms = BotCommunicationEngine(db_session)
    council = BotCouncil(db_session, comms)
    council.convene(
        opinions=[
            CouncilOpinion(bot_id="bot-1", verdict="APPROVE", confidence=0.8, reasoning="liquidity looks fine"),
            CouncilOpinion(bot_id="bot-2", verdict="APPROVE", confidence=0.6, reasoning="agree"),
        ],
        topic_bot_id="bot-1",
    )
    db_session.commit()

    # This test's db_session and the API client's own session point at
    # different databases (different Settings), so this only exercises
    # the engine -> DB write path directly, mirroring how
    # test_trade_suggestions.py separates that concern from endpoint
    # shape/auth checks (covered by the fixtures above).
    from broker_sakuma.db import models
    from sqlalchemy import select

    rows = list(db_session.execute(select(models.LearningEvent)).scalars())
    assert len(rows) == 1
    assert rows[0].kind == InfoClassification.AGENT_OPINION
    assert "APPROVE" in rows[0].title
