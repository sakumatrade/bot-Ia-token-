from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from broker_sakuma.api.app import create_app
from broker_sakuma.config import Settings
from broker_sakuma.core.enums import BotState
from broker_sakuma.db import models
from broker_sakuma.db.base import make_engine, make_session_factory

API_KEY = "test-secret-key"


@pytest.fixture()
def api_settings(tmp_path):
    db_path = tmp_path / "test_api.db"
    return Settings(
        database={"url": f"sqlite:///{db_path}"},
        local_api={"api_key": API_KEY},
    )


@pytest.fixture()
def client(api_settings):
    app = create_app(settings=api_settings)
    return TestClient(app)


@pytest.fixture()
def auth_headers():
    return {"X-API-Key": API_KEY}


def seed_session(settings):
    engine = make_engine(settings.database.url)
    return make_session_factory(engine)()


def test_missing_api_key_is_rejected(client):
    response = client.get("/api/status")
    assert response.status_code == 401


def test_wrong_api_key_is_rejected(client):
    response = client.get("/api/status", headers={"X-API-Key": "not-the-right-key"})
    assert response.status_code == 401


def test_unset_api_key_config_rejects_everyone(tmp_path):
    settings = Settings(database={"url": f"sqlite:///{tmp_path / 't.db'}"})  # local_api.api_key left unset
    app = create_app(settings=settings)
    client = TestClient(app)
    response = client.get("/api/status", headers={"X-API-Key": "anything"})
    assert response.status_code == 401


def test_status_endpoint_with_valid_key(client, auth_headers):
    response = client.get("/api/status", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["system_state"] == "ONLINE"
    assert body["live_trading_enabled"] is False


def test_dashboard_reflects_real_seeded_data_not_fake_numbers(client, auth_headers, api_settings):
    session = seed_session(api_settings)
    session.add(models.Bot(name="Son 300", state=BotState.ACTIVE, capital_operational_usd=42.0))
    session.commit()
    session.close()

    response = client.get("/api/dashboard", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["capital_operational_usd"] == 42.0
    assert body["active_bots"] == 1
    assert body["dead_bots"] == 0


def test_bots_endpoint_lists_seeded_bots(client, auth_headers, api_settings):
    session = seed_session(api_settings)
    session.add(models.Bot(name="Son 310", state=BotState.ACTIVE))
    session.commit()
    session.close()

    response = client.get("/api/bots", headers=auth_headers)
    assert response.status_code == 200
    names = [b["name"] for b in response.json()]
    assert "Son 310" in names


def test_system_start_then_pause_then_resume(client, auth_headers):
    r1 = client.post("/api/system/start", headers=auth_headers)
    assert r1.status_code == 200
    assert r1.json()["system_state"] == "ONLINE"

    r2 = client.post("/api/system/pause", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["system_state"] == "PAUSED"

    r3 = client.post("/api/system/resume", headers=auth_headers)
    assert r3.status_code == 200
    assert r3.json()["system_state"] == "ONLINE"


def test_kill_switch_requires_a_reason(client, auth_headers):
    response = client.post("/api/system/kill-switch", headers=auth_headers, json={"reason": ""})
    assert response.status_code == 422


def test_kill_switch_engage_then_resume_is_blocked(client, auth_headers):
    r1 = client.post("/api/system/kill-switch", headers=auth_headers, json={"reason": "suspicious wallet activity"})
    assert r1.status_code == 200
    assert r1.json()["system_state"] == "EMERGENCY_STOP"

    r2 = client.post("/api/system/resume", headers=auth_headers)
    assert r2.status_code == 409


def test_kill_switch_without_api_key_is_rejected(client):
    response = client.post("/api/system/kill-switch", json={"reason": "test"})
    assert response.status_code == 401


def test_empty_lists_are_returned_for_untouched_resources(client, auth_headers):
    for path in ("/api/opportunities", "/api/trades", "/api/strategies", "/api/alerts", "/api/research", "/api/protocols", "/api/loans", "/api/reserves", "/api/wallets"):
        response = client.get(path, headers=auth_headers)
        assert response.status_code == 200, path
        assert response.json() == []


def test_dashboard_page_is_public_but_serves_no_data(client):
    """The browser-based dashboard (spec: pragmatic cross-platform
    complement to the macOS app) is static markup only — it must load
    without an API key. The page's own JavaScript then calls the
    authenticated /api/* endpoints from the browser, same as the Safari
    extension.
    """

    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<script>" in response.text  # data comes from JS calling /api/*, not embedded here

    root_response = client.get("/", follow_redirects=False)
    assert root_response.status_code in (302, 307)
    assert root_response.headers["location"] == "/dashboard"


def test_add_wallet_is_always_watch_only(client, auth_headers):
    response = client.post(
        "/api/wallets",
        headers=auth_headers,
        json={
            "name": "Minha carteira Phantom",
            "blockchain": "solana",
            "wallet_type": "RECEIVING_WALLET",
            "public_address": "3xampleSolanaPublicAddress1111111111111",
            "purpose": "acompanhar saldo",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["kind"] == "WATCH_ONLY"
    assert body["public_address"] == "3xampleSolanaPublicAddress1111111111111"

    listed = client.get("/api/wallets", headers=auth_headers).json()
    assert any(w["id"] == body["id"] for w in listed)


def test_add_wallet_rejects_invalid_wallet_type(client, auth_headers):
    response = client.post(
        "/api/wallets",
        headers=auth_headers,
        json={"name": "X", "wallet_type": "NOT_A_REAL_TYPE", "public_address": "Addr1"},
    )
    assert response.status_code == 422


def test_add_wallet_rejects_duplicate_address(client, auth_headers):
    payload = {
        "name": "A",
        "blockchain": "solana",
        "wallet_type": "BOT_WALLET",
        "public_address": "DupAddr1111111111111111111111111111111",
    }
    first = client.post("/api/wallets", headers=auth_headers, json=payload)
    assert first.status_code == 201

    second = client.post("/api/wallets", headers=auth_headers, json={**payload, "name": "B"})
    assert second.status_code == 409


def test_add_wallet_requires_api_key(client):
    response = client.post(
        "/api/wallets",
        json={"name": "X", "wallet_type": "BOT_WALLET", "public_address": "Addr1"},
    )
    assert response.status_code == 401


def test_growth_endpoint_reports_configured_limits(client, auth_headers):
    response = client.get("/api/growth", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["max_bots"] > 0
    assert body["total_bots"] == 0
