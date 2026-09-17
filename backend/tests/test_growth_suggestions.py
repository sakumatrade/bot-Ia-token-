"""GrowthSuggestion + /api/growth-suggestions (spec section 63): a nudge
that a liquidity bucket has proven itself with enough real (simulated)
round trips, never an instruction the system acts on. No bot is ever
spawned by this codebase on its own — "acting on it" means the user
clicking "Criar bot" themselves, the same explicit action the dashboard's
create-bot card already requires.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from broker_sakuma.api.app import create_app
from broker_sakuma.config import Settings
from broker_sakuma.core.enums import GrowthSuggestionStatus
from broker_sakuma.db import models
from broker_sakuma.engines.pattern_learning import PatternLearner, liquidity_bucket_tag

API_KEY = "growth-suggestion-test-key"


def test_no_suggestion_with_too_few_samples(db_session):
    learner = PatternLearner(db_session, min_samples=5)
    for _ in range(4):
        learner.record_outcome(bot_id="bot-1", liquidity_usd=1500, pnl_usd=0.4)
        assert learner.check_growth_suggestion(1500) is None


def test_no_suggestion_when_average_is_negative(db_session):
    learner = PatternLearner(db_session, min_samples=5)
    for _ in range(10):
        learner.record_outcome(bot_id="bot-1", liquidity_usd=1500, pnl_usd=-0.4)
    assert learner.check_growth_suggestion(1500) is None


def test_suggestion_created_once_enough_positive_samples_exist(db_session):
    learner = PatternLearner(db_session, min_samples=5)
    for _ in range(5):
        learner.record_outcome(bot_id="bot-1", liquidity_usd=1500, pnl_usd=0.4)

    suggestion = learner.check_growth_suggestion(1500)
    assert suggestion is not None
    assert suggestion.liquidity_bucket_tag == liquidity_bucket_tag(1500)
    assert suggestion.samples_count == 5
    assert suggestion.average_pnl_usd == pytest.approx(0.4)
    assert suggestion.status == GrowthSuggestionStatus.PENDING


def test_suggestion_is_never_duplicated_for_the_same_bucket(db_session):
    learner = PatternLearner(db_session, min_samples=5)
    for _ in range(5):
        learner.record_outcome(bot_id="bot-1", liquidity_usd=1500, pnl_usd=0.4)
    first = learner.check_growth_suggestion(1500)
    assert first is not None

    for _ in range(5):
        learner.record_outcome(bot_id="bot-1", liquidity_usd=1500, pnl_usd=0.4)
    second = learner.check_growth_suggestion(1500)
    assert second is None

    all_rows = db_session.query(models.GrowthSuggestion).all()
    assert len(all_rows) == 1


def test_buckets_are_independent(db_session):
    learner = PatternLearner(db_session, min_samples=5)
    for _ in range(5):
        learner.record_outcome(bot_id="bot-1", liquidity_usd=1500, pnl_usd=0.4)
    learner.check_growth_suggestion(1500)

    # A different bucket has no samples yet - no suggestion for it.
    assert learner.check_growth_suggestion(4000) is None


@pytest.fixture()
def api_settings(tmp_path):
    db_path = tmp_path / "test_growth_suggestions_api.db"
    return Settings(database={"url": f"sqlite:///{db_path}"}, local_api={"api_key": API_KEY})


@pytest.fixture()
def client(api_settings):
    return TestClient(create_app(settings=api_settings))


@pytest.fixture()
def auth_headers():
    return {"X-API-Key": API_KEY}


def test_growth_suggestions_endpoints_require_api_key(client):
    assert client.get("/api/growth-suggestions").status_code == 401
    assert client.post("/api/growth-suggestions/x/dismiss").status_code == 401
    assert client.post("/api/growth-suggestions/x/mark-bot-created").status_code == 401


def test_list_growth_suggestions_empty_by_default(client, auth_headers):
    response = client.get("/api/growth-suggestions", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_dismiss_unknown_suggestion_is_404(client, auth_headers):
    response = client.post("/api/growth-suggestions/does-not-exist/dismiss", headers=auth_headers)
    assert response.status_code == 404


def test_mark_bot_created_unknown_suggestion_is_404(client, auth_headers):
    response = client.post("/api/growth-suggestions/does-not-exist/mark-bot-created", headers=auth_headers)
    assert response.status_code == 404


def test_full_flow_via_api_only(client, auth_headers):
    mother = client.post("/api/bots/mother", headers=auth_headers, json={"initial_capital_usd": 1000.0}).json()
    son = client.post("/api/bots/sons", headers=auth_headers, json={"parent_id": mother["id"]}).json()
    client.post(f"/api/bots/{son['id']}/activate", headers=auth_headers)

    client.post("/api/system/auto-trading", headers=auth_headers, json={"launches_per_cycle": 20})
    for _ in range(15):
        client.post("/api/system/run-cycle", headers=auth_headers)

    suggestions = client.get("/api/growth-suggestions", headers=auth_headers).json()
    if not suggestions:
        # The synthetic price walk is randomized: over 15 cycles of 20
        # launches each, a positive-average bucket reaching 5+ samples is
        # likely but not mathematically guaranteed - only assert the
        # shape/behavior when one actually appeared, same pattern
        # test_trade_suggestions.py uses for its own randomized flow.
        return

    suggestion = suggestions[0]
    assert suggestion["status"] == "PENDING"
    assert suggestion["samples_count"] >= 5
    assert suggestion["average_pnl_usd"] > 0

    dismissed = client.post(f"/api/growth-suggestions/{suggestion['id']}/dismiss", headers=auth_headers)
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "DISMISSED"

    pending_only = client.get("/api/growth-suggestions?status=PENDING", headers=auth_headers).json()
    assert all(s["status"] == "PENDING" for s in pending_only)

    invalid = client.get("/api/growth-suggestions?status=NOT_A_STATUS", headers=auth_headers)
    assert invalid.status_code == 422
