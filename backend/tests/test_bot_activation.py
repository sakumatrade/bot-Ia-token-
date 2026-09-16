"""Terminal/curl-friendly bot lifecycle endpoints (spec sections 7, 8, 10).

Covers POST /api/bots/mother, POST /api/bots/sons and
POST /api/bots/{id}/activate — all simulated capital, no wallet or
blockchain call anywhere in this flow.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from broker_sakuma.api.app import create_app
from broker_sakuma.config import Settings

API_KEY = "activation-test-key"


@pytest.fixture()
def api_settings(tmp_path):
    db_path = tmp_path / "test_bot_activation.db"
    return Settings(database={"url": f"sqlite:///{db_path}"}, local_api={"api_key": API_KEY})


@pytest.fixture()
def client(api_settings):
    return TestClient(create_app(settings=api_settings))


@pytest.fixture()
def auth_headers():
    return {"X-API-Key": API_KEY}


def test_create_mother_bot(client, auth_headers):
    response = client.post(
        "/api/bots/mother", headers=auth_headers, json={"name": "Mother Bot", "initial_capital_usd": 1000.0}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Mother Bot"
    assert body["generation"] == 0
    assert body["parent_id"] is None
    assert body["capital_operational_usd"] == 1000.0
    assert body["state"] == "ACTIVE"


def test_cannot_create_a_second_mother_bot(client, auth_headers):
    client.post("/api/bots/mother", headers=auth_headers, json={"initial_capital_usd": 500.0})
    response = client.post("/api/bots/mother", headers=auth_headers, json={"initial_capital_usd": 500.0})
    assert response.status_code == 409


def test_spawn_son_under_mother(client, auth_headers):
    mother = client.post("/api/bots/mother", headers=auth_headers, json={"initial_capital_usd": 1000.0}).json()

    response = client.post(
        "/api/bots/sons", headers=auth_headers, json={"parent_id": mother["id"], "name": "Son 001"}
    )
    assert response.status_code == 201
    son = response.json()
    assert son["name"] == "Son 001"
    assert son["generation"] == 1
    assert son["parent_id"] == mother["id"]
    assert son["capital_operational_usd"] == 0.0
    assert son["state"] == "CREATED"


def test_spawn_son_rejects_unknown_parent(client, auth_headers):
    response = client.post("/api/bots/sons", headers=auth_headers, json={"parent_id": "does-not-exist"})
    assert response.status_code == 404


def test_activate_bot_funds_it_with_exactly_five_dollars(client, auth_headers):
    mother = client.post("/api/bots/mother", headers=auth_headers, json={"initial_capital_usd": 1000.0}).json()
    son = client.post("/api/bots/sons", headers=auth_headers, json={"parent_id": mother["id"]}).json()

    response = client.post(f"/api/bots/{son['id']}/activate", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()

    assert body["initial_capital_usd"] == 5.0
    assert body["bot"]["state"] == "ACTIVE"
    assert body["bot"]["capital_operational_usd"] == 5.0
    assert body["bot"]["capital_borrowed_usd"] == 5.0

    mother_after = next(b for b in client.get("/api/bots", headers=auth_headers).json() if b["id"] == mother["id"])
    assert mother_after["capital_operational_usd"] == 995.0

    loans = client.get("/api/loans", headers=auth_headers).json()
    assert len(loans) == 1
    assert loans[0]["principal_usd"] == 5.0
    assert loans[0]["bot_id"] == son["id"]


def test_activate_bot_requires_5_dollars_regardless_of_requested_amount(client, auth_headers):
    """The $5 rule (spec section 10) is structural: there is no field in
    the activate request to ask for a different starting amount at all."""

    mother = client.post("/api/bots/mother", headers=auth_headers, json={"initial_capital_usd": 1000.0}).json()
    son = client.post("/api/bots/sons", headers=auth_headers, json={"parent_id": mother["id"]}).json()

    response = client.post(f"/api/bots/{son['id']}/activate", headers=auth_headers, json={"initial_capital_usd": 500.0})
    assert response.status_code == 200
    assert response.json()["initial_capital_usd"] == 5.0


def test_cannot_activate_unknown_bot(client, auth_headers):
    response = client.post("/api/bots/does-not-exist/activate", headers=auth_headers)
    assert response.status_code == 404


def test_cannot_activate_the_mother_bot_itself(client, auth_headers):
    mother = client.post("/api/bots/mother", headers=auth_headers, json={"initial_capital_usd": 1000.0}).json()
    response = client.post(f"/api/bots/{mother['id']}/activate", headers=auth_headers)
    assert response.status_code == 409


def test_activation_endpoints_require_api_key(client):
    r1 = client.post("/api/bots/mother", json={"initial_capital_usd": 1000.0})
    r2 = client.post("/api/bots/sons", json={"parent_id": "x"})
    r3 = client.post("/api/bots/x/activate")
    assert r1.status_code == 401
    assert r2.status_code == 401
    assert r3.status_code == 401
