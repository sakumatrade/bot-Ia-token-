"""Read-only API key (spec: a free, view-only link for people watching
the bot learn - see config.py's LocalAPIConfig.read_only_api_key and
api/deps.py's require_api_key). No deposit, no wallet, and the backend
itself rejects every state-changing request made with this key, never
relying on the dashboard's UI alone to hide the button.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from broker_sakuma.api.app import create_app
from broker_sakuma.config import Settings

MAIN_KEY = "main-secret-key"
READ_ONLY_KEY = "viewer-secret-key"


@pytest.fixture()
def api_settings(tmp_path):
    db_path = tmp_path / "test_readonly_api.db"
    return Settings(
        database={"url": f"sqlite:///{db_path}"},
        local_api={"api_key": MAIN_KEY, "read_only_api_key": READ_ONLY_KEY},
    )


@pytest.fixture()
def client(api_settings):
    return TestClient(create_app(settings=api_settings))


def test_main_key_can_read_and_write(client):
    get_response = client.get("/api/dashboard", headers={"X-API-Key": MAIN_KEY})
    assert get_response.status_code == 200

    post_response = client.post("/api/system/pause", headers={"X-API-Key": MAIN_KEY})
    assert post_response.status_code == 200


def test_read_only_key_can_read(client):
    response = client.get("/api/dashboard", headers={"X-API-Key": READ_ONLY_KEY})
    assert response.status_code == 200


def test_read_only_key_cannot_write(client):
    response = client.post("/api/system/pause", headers={"X-API-Key": READ_ONLY_KEY})
    assert response.status_code == 403

    response = client.post(
        "/api/bots/sons", headers={"X-API-Key": READ_ONLY_KEY}, json={"parent_id": "does-not-matter"}
    )
    assert response.status_code == 403


def test_wrong_key_is_still_rejected(client):
    response = client.get("/api/dashboard", headers={"X-API-Key": "neither-key"})
    assert response.status_code == 401


def test_whoami_reports_read_only_correctly(client):
    main_who = client.get("/api/system/whoami", headers={"X-API-Key": MAIN_KEY}).json()
    assert main_who == {"read_only": False}

    viewer_who = client.get("/api/system/whoami", headers={"X-API-Key": READ_ONLY_KEY}).json()
    assert viewer_who == {"read_only": True}


def test_no_read_only_key_configured_means_only_main_key_works(tmp_path):
    settings = Settings(
        database={"url": f"sqlite:///{tmp_path / 't2.db'}"},
        local_api={"api_key": MAIN_KEY},  # read_only_api_key left unset
    )
    client = TestClient(create_app(settings=settings))

    assert client.get("/api/dashboard", headers={"X-API-Key": MAIN_KEY}).status_code == 200
    assert client.get("/api/dashboard", headers={"X-API-Key": READ_ONLY_KEY}).status_code == 401
