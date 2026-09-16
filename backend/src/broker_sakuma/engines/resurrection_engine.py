"""BotResurrectionEngine (spec sections 15, 16): after a post-mortem and a
learning step, a dead bot may be reborn as a new, explicitly versioned bot
that references its predecessor's failure and the correction applied.

The reborn bot starts with zero capital; its first thesis still has to go
through ThesisEngine.start_initial_test, which always allocates the
configured $5 regardless of anything else in the system (spec section 16:
"mesmo que Mother Bot possua capital disponível").
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from broker_sakuma.core.enums import BotLifecycleEventType, BotState, InfoClassification
from broker_sakuma.db import models
from broker_sakuma.engines.collective_memory import CollectiveMemoryStore
from broker_sakuma.engines.lineage_engine import LineageEngine


class ResurrectionError(Exception):
    pass


class BotResurrectionEngine:
    def __init__(self, session: Session, lineage_engine: LineageEngine, collective_memory: CollectiveMemoryStore):
        self.session = session
        self.lineage_engine = lineage_engine
        self.collective_memory = collective_memory

    def _next_version_name(self, dead_bot: models.Bot) -> str:
        count_stmt = select(func.count(models.BotLineage.id)).where(
            models.BotLineage.parent_id == dead_bot.id,
            models.BotLineage.relationship_type == "resurrection",
        )
        prior_resurrections = self.session.execute(count_stmt).scalar_one()
        return f"{dead_bot.name}-R{prior_resurrections + 1}"

    def resurrect(
        self,
        dead_bot: models.Bot,
        post_mortem: models.PostMortem,
        correction: str,
    ) -> models.Bot:
        if dead_bot.state != BotState.DEAD:
            raise ResurrectionError(f"bot {dead_bot.id} is not DEAD (state={dead_bot.state}); cannot resurrect")
        if post_mortem.bot_id != dead_bot.id:
            raise ResurrectionError("post_mortem does not belong to dead_bot")

        new_name = self._next_version_name(dead_bot)
        new_version = str(int(dead_bot.version) + 1) if dead_bot.version.isdigit() else f"{dead_bot.version}+1"

        new_bot = self.lineage_engine.spawn_son(
            parent=dead_bot,
            name=new_name,
            relationship_type="resurrection",
            reason=f"Resurrection after loss: {post_mortem.probable_cause}",
            previous_failure=post_mortem.probable_cause,
            correction=correction,
        )
        new_bot.version = new_version
        self.session.add(new_bot)

        self.session.add(
            models.BotLifecycleEvent(
                bot_id=dead_bot.id,
                event_type=BotLifecycleEventType.RESURRECTED,
                from_state=BotState.DEAD.value,
                to_state=BotState.DEAD.value,
                reason=f"superseded by {new_name} ({new_bot.id})",
            )
        )
        self.session.commit()

        self.collective_memory.record_from_post_mortem(
            post_mortem,
            bot=dead_bot,
            title=f"{dead_bot.name} died: {post_mortem.probable_cause}",
            tags=["resurrection", "post_mortem"],
        )
        self.collective_memory.record(
            source_bot_id=new_bot.id,
            kind=InfoClassification.HYPOTHESIS,
            title=f"{new_name} correction over {dead_bot.name}",
            content=correction,
            tags=["resurrection", "correction"],
            post_mortem_id=post_mortem.id,
        )

        return new_bot
