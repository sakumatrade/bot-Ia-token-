"""Mother Bot / Son lineage (spec sections 7, 8): the Mother Bot coordinates
but never overrides safety rules, and every Son is a real row with a
parent_id, generation and full lifecycle trail.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from broker_sakuma.config import GrowthPolicyConfig, MaximumLossPolicyConfig
from broker_sakuma.core.enums import BotLifecycleEventType, BotState
from broker_sakuma.db import models


class GrowthPolicyViolation(Exception):
    """Raised when spawning a bot would exceed the configured growth limits
    (spec section 63). Growth may never alter safety rules to work around
    this — the caller must fix the underlying condition, not the policy."""


class LineageEngine:
    def __init__(self, session: Session, growth_config: GrowthPolicyConfig, max_loss_config: MaximumLossPolicyConfig):
        self.session = session
        self.growth_config = growth_config
        self.max_loss_config = max_loss_config

    def create_mother_bot(self, name: str = "Mother Bot", initial_capital_usd: float = 0.0) -> models.Bot:
        mother = models.Bot(
            name=name,
            parent_id=None,
            generation=0,
            state=BotState.ACTIVE,
            capital_operational_usd=initial_capital_usd,
            peak_equity_usd=initial_capital_usd,
            max_loss_usd=self.max_loss_config.per_bot_max_loss_usd,
        )
        self.session.add(mother)
        self.session.commit()

        self.session.add(
            models.BotLineage(bot_id=mother.id, parent_id=None, generation=0, relationship_type="root")
        )
        self.session.add(
            models.BotLifecycleEvent(
                bot_id=mother.id,
                event_type=BotLifecycleEventType.CREATED,
                to_state=BotState.ACTIVE.value,
                reason="mother bot bootstrap",
            )
        )
        self.session.add(
            models.AuditLog(
                actor="lineage_engine",
                action="MOTHER_BOT_CREATED",
                entity_type="bot",
                entity_id=mother.id,
                details={"initial_capital_usd": initial_capital_usd},
            )
        )
        self.session.commit()
        return mother

    def _bot_count(self) -> int:
        return self.session.execute(select(func.count(models.Bot.id))).scalar_one()

    def spawn_son(
        self,
        parent: models.Bot,
        name: str | None = None,
        relationship_type: str = "child",
        reason: str | None = None,
        previous_failure: str | None = None,
        correction: str | None = None,
    ) -> models.Bot:
        """Spawn a new Son bot under ``parent``. The son is created with
        zero capital: funding is a separate, explicit act (LoanEngine /
        ThesisEngine), never implicit here.
        """

        next_generation = parent.generation + 1
        if next_generation > self.growth_config.max_generations:
            raise GrowthPolicyViolation(
                f"generation {next_generation} exceeds max_generations={self.growth_config.max_generations}"
            )
        if self._bot_count() >= self.growth_config.max_bots:
            raise GrowthPolicyViolation(f"max_bots={self.growth_config.max_bots} already reached")

        son_name = name or f"Son {self._bot_count():03d}"
        son = models.Bot(
            name=son_name,
            parent_id=parent.id,
            generation=next_generation,
            state=BotState.CREATED,
            max_loss_usd=self.max_loss_config.per_bot_max_loss_usd,
        )
        self.session.add(son)
        self.session.commit()

        self.session.add(
            models.BotLineage(
                bot_id=son.id,
                parent_id=parent.id,
                generation=next_generation,
                relationship_type=relationship_type,
                reason=reason,
                previous_failure=previous_failure,
                correction=correction,
            )
        )
        self.session.add(
            models.BotLifecycleEvent(
                bot_id=son.id,
                event_type=BotLifecycleEventType.CREATED,
                to_state=BotState.CREATED.value,
                reason=reason or f"spawned by {parent.name}",
            )
        )
        self.session.add(
            models.AuditLog(
                actor="lineage_engine",
                action="BOT_SPAWNED",
                entity_type="bot",
                entity_id=son.id,
                details={"parent_id": parent.id, "generation": next_generation},
            )
        )
        self.session.commit()
        return son

    def lineage_tree(self, root_bot_id: str) -> dict:
        """Return a nested dict representing the lineage tree rooted at
        ``root_bot_id``, for the lineage-tree view (spec section 8)."""

        bot = self.session.get(models.Bot, root_bot_id)
        if bot is None:
            raise ValueError(f"bot {root_bot_id} not found")

        children_stmt = select(models.Bot).where(models.Bot.parent_id == root_bot_id)
        children = self.session.execute(children_stmt).scalars().all()
        return {
            "id": bot.id,
            "name": bot.name,
            "generation": bot.generation,
            "state": bot.state.value if hasattr(bot.state, "value") else bot.state,
            "children": [self.lineage_tree(child.id) for child in children],
        }
