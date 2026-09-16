"""CollectiveMemory (spec section 14): the knowledge of a dead bot survives
it. The Mother Bot and other bots can query it before repeating a failure.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from broker_sakuma.core.enums import InfoClassification
from broker_sakuma.db import models


class CollectiveMemoryStore:
    def __init__(self, session: Session):
        self.session = session

    def record_from_post_mortem(
        self,
        post_mortem: models.PostMortem,
        bot: models.Bot,
        title: str,
        tags: list[str] | None = None,
    ) -> models.CollectiveMemory:
        entry = models.CollectiveMemory(
            source_bot_id=bot.id,
            post_mortem_id=post_mortem.id,
            kind=InfoClassification.REAL_RESULT,
            title=title,
            content=post_mortem.probable_cause,
            tags=tags or [],
        )
        self.session.add(entry)
        self.session.commit()
        return entry

    def record(
        self,
        source_bot_id: str,
        kind: InfoClassification,
        title: str,
        content: str | None = None,
        tags: list[str] | None = None,
        post_mortem_id: str | None = None,
    ) -> models.CollectiveMemory:
        entry = models.CollectiveMemory(
            source_bot_id=source_bot_id,
            post_mortem_id=post_mortem_id,
            kind=kind,
            title=title,
            content=content,
            tags=tags or [],
        )
        self.session.add(entry)
        self.session.commit()
        return entry

    def find_by_tags(self, tags: list[str]) -> list[models.CollectiveMemory]:
        """Return every memory entry that shares at least one tag with
        ``tags``. Used before spawning a new thesis so a bot can check
        whether this situation has already caused a failure before.
        """

        wanted = set(tags)
        all_entries = self.session.execute(select(models.CollectiveMemory)).scalars().all()
        return [entry for entry in all_entries if wanted & set(entry.tags)]
