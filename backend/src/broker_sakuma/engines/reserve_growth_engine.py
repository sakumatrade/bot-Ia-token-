"""ReserveGrowthEngine (spec section 20): each bot builds its own reserve,
distinct from operational capital, borrowed capital, and Mother's
patrimony. However large a bot's reserve grows, a brand-new thesis still
starts at the configured $5 (enforced structurally by ThesisEngine, which
never reads the reserve at all).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from broker_sakuma.db import models


class ReserveGrowthEngine:
    def __init__(self, session: Session):
        self.session = session

    def get_or_create(self, bot_id: str | None) -> models.Reserve:
        stmt = select(models.Reserve).where(models.Reserve.bot_id == bot_id)
        reserve = self.session.execute(stmt).scalar_one_or_none()
        if reserve is None:
            reserve = models.Reserve(bot_id=bot_id, balance_usd=0.0)
            self.session.add(reserve)
            self.session.commit()
        return reserve

    def contribute(self, bot_id: str | None, amount_usd: float, reason: str) -> models.Reserve:
        if amount_usd < 0:
            raise ValueError("reserve contributions cannot be negative")

        reserve = self.get_or_create(bot_id)
        reserve.balance_usd += amount_usd
        self.session.add(reserve)

        if bot_id is not None:
            bot = self.session.get(models.Bot, bot_id)
            if bot is not None:
                bot.reserve_usd = reserve.balance_usd
                self.session.add(bot)

        self.session.add(
            models.AuditLog(
                actor="reserve_growth_engine",
                action="RESERVE_CONTRIBUTION",
                entity_type="reserve",
                entity_id=reserve.id,
                details={"bot_id": bot_id, "amount_usd": amount_usd, "reason": reason},
            )
        )
        self.session.commit()
        return reserve
