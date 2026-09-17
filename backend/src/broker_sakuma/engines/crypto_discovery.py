"""CryptoDiscoveryEngine, RevenueDiscoveryEngine, CryptoResearchLab
(spec sections 23, 25).

DominusBot isn't limited to Pump.fun: this is where DEX, DeFi,
arbitrage, staking, lending, liquidity pools, launchpads, yield,
infrastructure and cross-chain opportunities get logged. Research only —
registering an opportunity never executes anything.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from broker_sakuma.core.enums import InfoClassification, OpportunityCategory, ProtocolStatus
from broker_sakuma.db import models
from broker_sakuma.engines.learning_engine import LearningEngine


class CryptoDiscoveryEngine:
    def __init__(self, session: Session):
        self.session = session

    def register_opportunity(
        self,
        source: str,
        classification: InfoClassification,
        category: OpportunityCategory | None = None,
        description: str | None = None,
        protocol_id: str | None = None,
        token_id: str | None = None,
        risk_score: float | None = None,
        evidence: dict | None = None,
    ) -> models.Opportunity:
        opportunity = models.Opportunity(
            protocol_id=protocol_id,
            token_id=token_id,
            source=source,
            classification=classification,
            status="RESEARCH",
            risk_score=risk_score,
            description=description,
            evidence={**(evidence or {}), **({"category": category.value} if category else {})},
        )
        self.session.add(opportunity)
        self.session.commit()
        return opportunity

    def mark_ignored(self, opportunity: models.Opportunity, reason: str) -> models.Opportunity:
        """The system is allowed to just not act on an opportunity (spec
        section 22): it doesn't have to evaluate everything to a
        conclusion."""

        opportunity.status = "IGNORE"
        opportunity.evidence = {**opportunity.evidence, "ignore_reason": reason}
        self.session.add(opportunity)
        self.session.commit()
        return opportunity


class RevenueDiscoveryEngine:
    """A thin bridge from 'new revenue idea' to a tracked, classified
    opportunity plus a hypothesis on the shared learning feed."""

    def __init__(self, session: Session, discovery_engine: CryptoDiscoveryEngine, learning_engine: LearningEngine):
        self.session = session
        self.discovery_engine = discovery_engine
        self.learning_engine = learning_engine

    def propose_revenue_idea(
        self, source_bot_id: str | None, title: str, content: str
    ) -> tuple[models.LearningEvent, models.Opportunity]:
        event = self.learning_engine.propose_hypothesis(source_bot_id, title, content)
        opportunity = self.discovery_engine.register_opportunity(
            source="revenue_discovery",
            classification=InfoClassification.HYPOTHESIS,
            category=OpportunityCategory.OTHER,
            description=content,
        )
        return event, opportunity


class CryptoResearchLab:
    """Backs the Research Lab dashboard (spec section 25): protocols
    grouped by their current status."""

    def __init__(self, session: Session):
        self.session = session

    def board(self) -> dict[str, list[models.Protocol]]:
        protocols = list(self.session.execute(select(models.Protocol)).scalars())
        board: dict[str, list[models.Protocol]] = {status.value: [] for status in ProtocolStatus}
        for protocol in protocols:
            board[ProtocolStatus(protocol.status).value].append(protocol)
        return board
