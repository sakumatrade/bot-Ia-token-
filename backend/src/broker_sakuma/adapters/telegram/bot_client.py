"""TelegramBotClient: thin request/response wrapper over Telegram's real
Bot API. It makes no authorization or business decisions — it only sends
what ``TelegramControlService`` already decided to send.
"""

from __future__ import annotations

import httpx


class TelegramBotClient:
    def __init__(self, bot_token: str, transport: httpx.BaseTransport | None = None, timeout: float = 10.0):
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._client = httpx.Client(transport=transport, timeout=timeout)

    def send_message(self, chat_id: str, text: str) -> httpx.Response:
        return self._client.post(f"{self._base_url}/sendMessage", json={"chat_id": chat_id, "text": text})

    def get_updates(self, offset: int | None = None, timeout: int = 0) -> httpx.Response:
        params: dict[str, int] = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        return self._client.get(f"{self._base_url}/getUpdates", params=params)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "TelegramBotClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
