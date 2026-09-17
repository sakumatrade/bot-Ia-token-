"""Pause/resume individual bots (spec section 64's existing PAUSED state)
and live control of the autonomous PAPER-trading loop
(GET/POST /api/system/auto-trading) — no server restart needed to toggle
it, and a paused bot must not trade even when the loop is on. All
simulated capital only.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from broker_sakuma.api.app import create_app
from broker_sakuma.config import Settings

API_KEY = "pause-control-test-key"


@pytest.fixture()
def api_settings(tmp_path):
    db_path = tmp_path / "test_pause_control.db"
    return Settings(database={"url": f"sqlite:///{db_path}"}, local_api={"api_key": API_KEY})


@pytest.fixture()
def client(api_settings):
    return TestClient(create_app(settings=api_settings))


@pytest.fixture()
def auth_headers():
    return {"X-API-Key": API_KEY}


def _activated_son(client, auth_headers):
    mother = client.post("/api/bots/mother", headers=auth_headers, json={"initial_capital_usd": 1000.0}).json()
    son = client.post("/api/bots/sons", headers=auth_headers, json={"parent_id": mother["id"]}).json()
    client.post(f"/api/bots/{son['id']}/activate", headers=auth_headers)
    return son


def test_pause_and_resume_a_bot(client, auth_headers):
    son = _activated_son(client, auth_headers)

    paused = client.post(f"/api/bots/{son['id']}/pause", headers=auth_headers)
    assert paused.status_code == 200
    assert paused.json()["state"] == "PAUSED"

    resumed = client.post(f"/api/bots/{son['id']}/resume", headers=auth_headers)
    assert resumed.status_code == 200
    assert resumed.json()["state"] == "ACTIVE"


def test_pausing_is_idempotent(client, auth_headers):
    son = _activated_son(client, auth_headers)
    client.post(f"/api/bots/{son['id']}/pause", headers=auth_headers)
    second = client.post(f"/api/bots/{son['id']}/pause", headers=auth_headers)
    assert second.status_code == 200
    assert second.json()["state"] == "PAUSED"


def test_cannot_resume_a_bot_that_is_not_paused(client, auth_headers):
    son = _activated_son(client, auth_headers)
    response = client.post(f"/api/bots/{son['id']}/resume", headers=auth_headers)
    assert response.status_code == 409


def test_cannot_pause_unknown_bot(client, auth_headers):
    response = client.post("/api/bots/does-not-exist/pause", headers=auth_headers)
    assert response.status_code == 404


def test_pause_and_resume_require_api_key(client):
    assert client.post("/api/bots/x/pause").status_code == 401
    assert client.post("/api/bots/x/resume").status_code == 401


def test_paused_bot_is_skipped_by_the_autonomous_cycle(client, auth_headers):
    son = _activated_son(client, auth_headers)
    client.post(f"/api/bots/{son['id']}/pause", headers=auth_headers)

    for _ in range(5):
        client.post("/api/system/run-cycle", headers=auth_headers)

    trades = client.get("/api/trades", headers=auth_headers).json()
    son_trades = [t for t in trades if t["bot_id"] == son["id"]]
    assert son_trades == []


def test_auto_trading_status_defaults_to_disabled(client, auth_headers):
    response = client.get("/api/system/auto-trading", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["running"] is False


def test_auto_trading_endpoints_require_api_key(client):
    assert client.get("/api/system/auto-trading").status_code == 401
    assert client.post("/api/system/auto-trading", json={"enabled": True}).status_code == 401


def test_can_update_auto_trading_parameters_without_enabling(client, auth_headers):
    response = client.post(
        "/api/system/auto-trading",
        headers=auth_headers,
        json={"interval_seconds": 30, "launches_per_cycle": 3, "position_fraction_of_capital": 0.25},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["running"] is False
    assert body["interval_seconds"] == 30
    assert body["launches_per_cycle"] == 3
    assert body["position_fraction_of_capital"] == 0.25


def test_toggling_auto_trading_on_starts_the_live_background_task(client, auth_headers):
    with client:  # runs the app's lifespan so the event loop exists for the background task
        response = client.post("/api/system/auto-trading", headers=auth_headers, json={"enabled": True})
        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] is True
        assert body["running"] is True

        off = client.post("/api/system/auto-trading", headers=auth_headers, json={"enabled": False})
        assert off.json()["enabled"] is False
        assert off.json()["running"] is False


def test_rejects_invalid_auto_trading_values(client, auth_headers):
    assert client.post(
        "/api/system/auto-trading", headers=auth_headers, json={"interval_seconds": 0}
    ).status_code == 422
    assert client.post(
        "/api/system/auto-trading", headers=auth_headers, json={"position_fraction_of_capital": 1.5}
    ).status_code == 422
