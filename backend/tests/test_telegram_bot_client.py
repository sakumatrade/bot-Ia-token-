from __future__ import annotations

import json

import httpx

from broker_sakuma.adapters.telegram.bot_client import TelegramBotClient


def test_send_message_hits_the_real_documented_endpoint_shape():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    transport = httpx.MockTransport(handler)
    client = TelegramBotClient("FAKE_TOKEN_FOR_TEST", transport=transport)

    response = client.send_message(chat_id="12345", text="Broker Sakuma is online")

    assert response.status_code == 200
    assert captured["url"] == "https://api.telegram.org/botFAKE_TOKEN_FOR_TEST/sendMessage"
    assert captured["body"] == {"chat_id": "12345", "text": "Broker Sakuma is online"}
    client.close()


def test_get_updates_passes_offset_as_query_param():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"ok": True, "result": []})

    transport = httpx.MockTransport(handler)
    with TelegramBotClient("FAKE_TOKEN_FOR_TEST", transport=transport) as client:
        client.get_updates(offset=42)

    assert "offset=42" in captured["url"]


def test_client_surfaces_telegram_error_responses_without_swallowing_them():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})

    transport = httpx.MockTransport(handler)
    with TelegramBotClient("BAD_TOKEN", transport=transport) as client:
        response = client.send_message(chat_id="1", text="hi")

    assert response.status_code == 401
    assert response.json()["ok"] is False
