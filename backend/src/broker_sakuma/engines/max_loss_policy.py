"""MaximumLossPolicy (spec section 12): a bot must die when it reaches its
maximum permitted loss. Death blocks new trades, new theses, transfers and
capital increases — enforced by checking ``Bot.state != DEAD`` at every
entry point that touches money (PaperExecutor, ThesisEngine, LoanEngine).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from broker_sakuma.core.enums import BotLifecycleEventType, BotState
from broker_sakuma.db import models


class MaximumLossPolicy:
    @staticmethod
    def has_breached(bot: models.Bot) -> bool:
        """A bot's own ``max_loss_usd`` is its ceiling, set at creation time
        from the global ``MaximumLossPolicyConfig`` default but tracked
        per-bot from then on (spec: "Cada bot possui uma perda máxima
        permitida")."""

        return bot.cumulative_pnl_usd <= -abs(bot.max_loss_usd)

    def enforce(self, session: Session, bot: models.Bot, reason: str) -> bool:
        """Transition ``bot`` to DEAD if it has breached its max loss.

        Returns True if this call is what killed the bot (idempotent: a
        bot already DEAD is left untouched and returns False).
        """

        if bot.state == BotState.DEAD:
            return False
        if not self.has_breached(bot):
            return False

        # A bot freshly loaded from the DB in a new session comes back with
        # a plain str for this column (no SQLAlchemy Enum type is used),
        # not a BotState instance — BotState(...) normalizes either case.
        previous_state = BotState(bot.state) if bot.state else None
        bot.state = BotState.DEAD
        bot.died_at = datetime.now(timezone.utc)
        session.add(bot)
        session.add(
            models.BotLifecycleEvent(
                bot_id=bot.id,
                event_type=BotLifecycleEventType.DEAD,
                from_state=previous_state.value if previous_state else None,
                to_state=BotState.DEAD.value,
                reason=reason,
            )
        )
        session.add(
            models.RiskEvent(
                bot_id=bot.id,
                event_type="MAX_LOSS_BREACHED",
                severity="CRITICAL",
                details={
                    "cumulative_pnl_usd": bot.cumulative_pnl_usd,
                    "max_loss_usd": bot.max_loss_usd,
                    "reason": reason,
                },
            )
        )
        session.add(
            models.AuditLog(
                actor="max_loss_policy",
                action="BOT_DEAD",
                entity_type="bot",
                entity_id=bot.id,
                details={"reason": reason, "cumulative_pnl_usd": bot.cumulative_pnl_usd},
            )
        )
        session.commit()
        return True
