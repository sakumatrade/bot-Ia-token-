"""GET /api/system/risk-policy ("Dominus Risk" — spec section 28): the
same limits RiskEngine/MaximumLossPolicy already enforce on every
simulated order, exposed read-only for transparency. Nothing here can be
changed via this endpoint, so it's safe for the read-only viewer key too.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from broker_sakuma.api.app import create_app
from broker_sakuma.config import MaximumLossPolicyConfig, RiskPolicyConfig, Settings

MAIN_KEY = "risk-policy-test-key"
READ_ONLY_KEY = "risk-policy-viewer-key"


@pytest.fixture()
def api_settings(tmp_path):
    db_path = tmp_path / "test_risk_policy.db"
    return Settings(
        database={"url": f"sqlite:///{db_path}"},
        local_api={"api_key": MAIN_KEY, "read_only_api_key": READ_ONLY_KEY},
        risk=RiskPolicyConfig(
            max_position_usd=7.5,
            max_daily_loss_usd=60.0,
            max_drawdown_pct=0.3,
            max_slippage_pct=0.04,
            min_liquidity_usd=1500.0,
            max_trades_per_day=25,
            max_consecutive_losses=4,
            min_wallet_balance_usd=6.0,
        ),
        max_loss=MaximumLossPolicyConfig(per_bot_max_loss_usd=8.0, per_bot_max_loss_pct_of_capital=0.9),
    )


@pytest.fixture()
def client(api_settings):
    return TestClient(create_app(settings=api_settings))


def test_requires_api_key(client):
    assert client.get("/api/system/risk-policy").status_code == 401


def test_returns_configured_limits(client):
    response = client.get("/api/system/risk-policy", headers={"X-API-Key": MAIN_KEY})
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "max_position_usd": 7.5,
        "max_daily_loss_usd": 60.0,
        "max_drawdown_pct": 0.3,
        "max_slippage_pct": 0.04,
        "min_liquidity_usd": 1500.0,
        "max_trades_per_day": 25,
        "max_consecutive_losses": 4,
        "min_wallet_balance_usd": 6.0,
        "per_bot_max_loss_usd": 8.0,
        "per_bot_max_loss_pct_of_capital": 0.9,
    }


def test_read_only_viewer_key_can_also_read_it(client):
    response = client.get("/api/system/risk-policy", headers={"X-API-Key": READ_ONLY_KEY})
    assert response.status_code == 200
