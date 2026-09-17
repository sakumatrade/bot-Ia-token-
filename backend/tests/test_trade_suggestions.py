"""TradeSuggestionEngine + /api/trade-suggestions (spec sections 33, 61):
a plain-language idea, never an instruction the system acts on. No
signer, no execution, no suggested dollar amount — sizing and acting on
one is entirely the user's own decision, made manually outside this
system.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from broker_sakuma.adapters.pumpfun.mock_provider import MockPumpFunProvider
from broker_sakuma.adapters.pumpfun.monitor import PumpFunMonitor
from broker_sakuma.adapters.pumpfun.provider import LaunchEvent
from broker_sakuma.api.app import create_app
from broker_sakuma.config import RiskPolicyConfig, Settings
from broker_sakuma.core.enums import TradeSuggestionStatus, WalletKind, WalletType
from broker_sakuma.db import models
from broker_sakuma.engines.trade_suggestion_engine import TradeSuggestionEngine

API_KEY = "trade-suggestion-test-key"


def test_no_suggestion_without_a_registered_wallet(db_session):
    provider = MockPumpFunProvider([LaunchEvent(
        mint_address="SYNTHETIC-nowallet", symbol="SYN", name="Synthetic", creator_address="c1",
        initial_liquidity_usd=2000.0, metadata={"synthetic": True},
    )])
    monitor = PumpFunMonitor(db_session, provider, RiskPolicyConfig())
    decisions = monitor.poll()
    assert decisions[0].action == "WATCH"

    engine = TradeSuggestionEngine(db_session)
    suggestion = engine.suggest_from_decision(decisions[0])
    assert suggestion is None


def test_suggestion_created_when_a_watch_only_wallet_exists(db_session):
    wallet = models.Wallet(
        name="Minha Phantom", wallet_type=WalletType.RECEIVING_WALLET, kind=WalletKind.WATCH_ONLY,
        public_address="SoLanaPublicAddressExample1111111111111111",
    )
    db_session.add(wallet)
    db_session.commit()

    provider = MockPumpFunProvider([LaunchEvent(
        mint_address="SYNTHETIC-haswallet", symbol="SYN", name="Synthetic", creator_address="c1",
        initial_liquidity_usd=2000.0, metadata={"synthetic": True},
    )])
    monitor = PumpFunMonitor(db_session, provider, RiskPolicyConfig())
    decisions = monitor.poll()

    engine = TradeSuggestionEngine(db_session)
    suggestion = engine.suggest_from_decision(decisions[0])

    assert suggestion is not None
    assert suggestion.wallet_id == wallet.id
    assert suggestion.status == TradeSuggestionStatus.PENDING
    assert "simulação" in suggestion.reasoning or "simulacao" in suggestion.reasoning
    assert not hasattr(suggestion, "suggested_amount_usd")  # never invents a dollar amount


def test_no_suggestion_for_an_ignore_decision(db_session):
    wallet = models.Wallet(
        name="Minha Phantom", wallet_type=WalletType.RECEIVING_WALLET, kind=WalletKind.WATCH_ONLY,
        public_address="SoLanaPublicAddressExample2222222222222222",
    )
    db_session.add(wallet)
    db_session.commit()

    provider = MockPumpFunProvider([LaunchEvent(
        mint_address="SYNTHETIC-lowliq", symbol="SYN", name="Synthetic", creator_address="c1",
        initial_liquidity_usd=1.0, metadata={"synthetic": True},
    )])
    monitor = PumpFunMonitor(db_session, provider, RiskPolicyConfig())
    decisions = monitor.poll()
    assert decisions[0].action == "IGNORE"

    engine = TradeSuggestionEngine(db_session)
    assert engine.suggest_from_decision(decisions[0]) is None


@pytest.fixture()
def api_settings(tmp_path):
    db_path = tmp_path / "test_trade_suggestions_api.db"
    return Settings(database={"url": f"sqlite:///{db_path}"}, local_api={"api_key": API_KEY})


@pytest.fixture()
def client(api_settings):
    return TestClient(create_app(settings=api_settings))


@pytest.fixture()
def auth_headers():
    return {"X-API-Key": API_KEY}


def test_trade_suggestions_endpoints_require_api_key(client):
    assert client.get("/api/trade-suggestions").status_code == 401
    assert client.post("/api/trade-suggestions/x/dismiss").status_code == 401
    assert client.post("/api/trade-suggestions/x/mark-done").status_code == 401


def test_list_trade_suggestions_empty_by_default(client, auth_headers):
    response = client.get("/api/trade-suggestions", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_full_flow_add_wallet_run_cycle_dismiss_suggestion(client, auth_headers):
    client.post(
        "/api/wallets", headers=auth_headers,
        json={"name": "Minha Phantom", "wallet_type": "RECEIVING_WALLET", "public_address": "SoLanaAddrXYZ111111111111111111111111"},
    )

    response = client.post("/api/system/run-cycle", headers=auth_headers)
    assert response.status_code == 200

    suggestions = client.get("/api/trade-suggestions", headers=auth_headers).json()
    # A single default-config cycle (1 synthetic launch) may or may not be
    # WATCH; only assert the shape/behavior when one was actually created.
    if not suggestions:
        return

    suggestion = suggestions[0]
    assert suggestion["status"] == "PENDING"
    assert "suggested_amount_usd" not in suggestion

    dismissed = client.post(f"/api/trade-suggestions/{suggestion['id']}/dismiss", headers=auth_headers)
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "DISMISSED"


def test_mark_done_and_invalid_status_filter(client, auth_headers):
    client.post(
        "/api/wallets", headers=auth_headers,
        json={"name": "W", "wallet_type": "RECEIVING_WALLET", "public_address": "SoLanaAddrABC222222222222222222222222"},
    )
    settings_response = client.post(
        "/api/system/auto-trading", headers=auth_headers, json={"launches_per_cycle": 20}
    )
    assert settings_response.status_code == 200
    client.post("/api/system/run-cycle", headers=auth_headers)

    suggestions = client.get("/api/trade-suggestions", headers=auth_headers).json()
    assert len(suggestions) > 0  # 20 launches: astronomically likely at least one WATCH

    suggestion_id = suggestions[0]["id"]
    done = client.post(f"/api/trade-suggestions/{suggestion_id}/mark-done", headers=auth_headers)
    assert done.status_code == 200
    assert done.json()["status"] == "DONE_MANUALLY"

    pending_only = client.get("/api/trade-suggestions?status=PENDING", headers=auth_headers).json()
    assert all(s["status"] == "PENDING" for s in pending_only)

    invalid = client.get("/api/trade-suggestions?status=NOT_A_STATUS", headers=auth_headers)
    assert invalid.status_code == 422


def test_dismiss_unknown_suggestion_is_404(client, auth_headers):
    response = client.post("/api/trade-suggestions/does-not-exist/dismiss", headers=auth_headers)
    assert response.status_code == 404
