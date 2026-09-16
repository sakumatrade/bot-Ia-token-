"""Real-time Telegram notification whenever a trade realizes a profit —
what the user actually asked for ("notificação toda vez que o bot ganhou
dinheiro"), distinct from the section-37 end-of-day summary
(``telegram_control_service.build_daily_report``).

Requires a real bot token created via @BotFather on Telegram (see
docs/PHASES.md for the setup steps) — configured entirely through
``Settings.telegram`` (environment variables), never hardcoded, and
silently does nothing if it isn't configured rather than raising.
"""

from __future__ import annotations

from broker_sakuma.adapters.telegram.bot_client import TelegramBotClient
from broker_sakuma.config import TelegramConfig
from broker_sakuma.db import models


class ProfitNotifier:
    def __init__(self, config: TelegramConfig, client: TelegramBotClient | None = None):
        self.config = config
        self._client = client

    @property
    def is_configured(self) -> bool:
        return bool(self.config.enabled and self.config.bot_token and self.config.owner_user_id)

    def _client_or_create(self) -> TelegramBotClient:
        if self._client is None:
            if not self.config.bot_token:
                raise RuntimeError("cannot create a TelegramBotClient without a bot_token")
            self._client = TelegramBotClient(self.config.bot_token)
        return self._client

    def notify_profit(self, bot: models.Bot, trade: models.PaperTrade) -> bool:
        """Returns True if a notification was actually sent. Never sends
        anything if Telegram isn't configured, or if the trade wasn't
        actually profitable — no inventing good news.
        """

        if not self.is_configured:
            return False
        if trade.simulated_pnl_usd <= 0:
            return False

        text = (
            f"💰 {bot.name} ganhou dinheiro!\n"
            f"Lucro da operação: ${trade.simulated_pnl_usd:.2f}\n"
            f"P&L total do bot: ${bot.cumulative_pnl_usd:.2f}"
        )
        client = self._client_or_create()
        response = client.send_message(chat_id=self.config.owner_user_id, text=text)
        return response.status_code == 200
