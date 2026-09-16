"""BotCommunicationEngine + BotCouncil (spec section 9).

Bots share opportunities, results, strategies, hypotheses, errors, token
and creator intel, protocol conditions, backtests, paper trading results
and new ideas — but every single piece carries an explicit
``InfoClassification``, and a hypothesis is never treated as a fact.

This reuses ``LearningEvent`` as the shared bus (it already has the right
shape: source, classification, title, content, optional thesis link)
rather than introducing a parallel table for the same kind of row.
``CollectiveMemory`` (spec section 14) stays the separate, specifically
post-mortem-derived long-term memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from broker_sakuma.core.enums import InfoClassification
from broker_sakuma.db import models


class BotCommunicationEngine:
    def __init__(self, session: Session):
        self.session = session

    def broadcast(
        self,
        source_bot_id: str | None,
        kind: InfoClassification,
        title: str,
        content: str | None = None,
        related_thesis_id: str | None = None,
    ) -> models.LearningEvent:
        if not title.strip():
            raise ValueError("broadcast title cannot be empty")

        event = models.LearningEvent(
            source_bot_id=source_bot_id,
            kind=kind,
            title=title,
            content=content,
            related_thesis_id=related_thesis_id,
        )
        self.session.add(event)
        self.session.commit()
        return event

    def feed_since(
        self,
        since: datetime | None = None,
        kinds: list[InfoClassification] | None = None,
    ) -> list[models.LearningEvent]:
        stmt = select(models.LearningEvent).order_by(models.LearningEvent.created_at.asc())
        if since is not None:
            stmt = stmt.where(models.LearningEvent.created_at >= since)
        if kinds:
            stmt = stmt.where(models.LearningEvent.kind.in_([k.value for k in kinds]))
        return list(self.session.execute(stmt).scalars())

    def verified_ground_truth(self) -> list[models.LearningEvent]:
        """FACT / DATA / REAL_RESULT only — never HYPOTHESIS, SIMULATION or
        AGENT_OPINION. Callers that need to treat something as settled
        should read from here, not from the raw feed.
        """

        return self.feed_since(
            kinds=[InfoClassification.FACT, InfoClassification.DATA, InfoClassification.REAL_RESULT]
        )


@dataclass
class CouncilOpinion:
    bot_id: str
    verdict: str
    confidence: float
    reasoning: str


@dataclass
class CouncilVerdict:
    majority: str
    tally: dict[str, int]
    opinions: list[CouncilOpinion]


class BotCouncil:
    """Bots deliberate together, but the council's conclusion is always
    recorded as ``AGENT_OPINION`` — no amount of bots agreeing promotes a
    verdict to FACT (spec section 9: never treat a hypothesis as a fact).
    """

    def __init__(self, session: Session, communication_engine: BotCommunicationEngine):
        self.session = session
        self.communication_engine = communication_engine

    def convene(
        self,
        opinions: list[CouncilOpinion],
        topic_bot_id: str | None = None,
        related_thesis_id: str | None = None,
    ) -> CouncilVerdict:
        if not opinions:
            raise ValueError("cannot convene a council with no opinions")

        tally: dict[str, int] = {}
        for opinion in opinions:
            tally[opinion.verdict] = tally.get(opinion.verdict, 0) + 1
        majority = max(tally, key=lambda verdict: tally[verdict])

        verdict = CouncilVerdict(majority=majority, tally=tally, opinions=opinions)

        self.communication_engine.broadcast(
            source_bot_id=topic_bot_id,
            kind=InfoClassification.AGENT_OPINION,
            title=f"Bot Council verdict: {majority}",
            content=f"tally={tally}",
            related_thesis_id=related_thesis_id,
        )
        return verdict
