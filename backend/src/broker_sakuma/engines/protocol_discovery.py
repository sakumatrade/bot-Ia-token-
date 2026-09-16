"""ProtocolDiscoveryAgent + risk scoring (spec sections 23, 24).

Research never means execution: ``ProtocolStatus`` (see
``core.enums.ProtocolStatus``) has exactly four values — RESEARCH_ONLY,
PAPER_ELIGIBLE, REVIEW_REQUIRED, DISABLED — and there is no fifth "live"
status anywhere in this enum. That is the structural guarantee behind
"nunca passar diretamente de descoberta para operação real": there is
simply no status value a protocol could hold that means "approved for
real trading."
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from broker_sakuma.config import ProtocolRiskScoreConfig
from broker_sakuma.core.enums import ProtocolStatus
from broker_sakuma.db import models


def compute_risk_score(protocol: models.Protocol, config: ProtocolRiskScoreConfig) -> float:
    """0 (safest) to 100 (riskiest). Only uses evidence actually present on
    the protocol row — a missing field contributes nothing rather than a
    guessed value.
    """

    score = config.baseline_score

    audit_count = len(protocol.audits or [])
    score -= min(audit_count * config.audit_score_reduction_per_audit, config.max_audit_reduction)

    incident_count = len(protocol.incidents or [])
    score += incident_count * config.incident_score_penalty_per_incident

    if protocol.age_days is not None and protocol.age_days > 0:
        age_credit = min(protocol.age_days / config.age_days_for_full_credit, 1.0)
        score -= age_credit * config.max_age_score_reduction

    if protocol.tvl_usd is not None and protocol.tvl_usd > 0:
        tvl_credit = min(protocol.tvl_usd / config.tvl_usd_for_full_credit, 1.0)
        score -= tvl_credit * config.max_tvl_score_reduction

    return max(0.0, min(100.0, score))


class ProtocolTransitionError(Exception):
    pass


class ProtocolDiscoveryAgent:
    def __init__(self, session: Session, risk_config: ProtocolRiskScoreConfig):
        self.session = session
        self.risk_config = risk_config

    def register_protocol(
        self,
        name: str,
        blockchain: str,
        category: str | None = None,
        website: str | None = None,
        docs_url: str | None = None,
    ) -> models.Protocol:
        """Idempotent: re-discovering the same protocol returns the
        existing row rather than creating a duplicate."""

        existing = self.session.execute(
            select(models.Protocol).where(models.Protocol.name == name, models.Protocol.blockchain == blockchain)
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        protocol = models.Protocol(
            name=name,
            blockchain=blockchain,
            category=category,
            website=website,
            docs_url=docs_url,
            status=ProtocolStatus.RESEARCH_ONLY,
        )
        self.session.add(protocol)
        self.session.commit()
        return protocol

    def update_evidence(
        self,
        protocol: models.Protocol,
        *,
        tvl_usd: float | None = None,
        volume_24h_usd: float | None = None,
        age_days: int | None = None,
        audits: list | None = None,
        incidents: list | None = None,
    ) -> models.Protocol:
        """Only overwrites fields explicitly passed — never backfills a
        missing metric with a fabricated default."""

        if tvl_usd is not None:
            protocol.tvl_usd = tvl_usd
        if volume_24h_usd is not None:
            protocol.volume_24h_usd = volume_24h_usd
        if age_days is not None:
            protocol.age_days = age_days
        if audits is not None:
            protocol.audits = audits
        if incidents is not None:
            protocol.incidents = incidents

        protocol.risk_score = compute_risk_score(protocol, self.risk_config)
        self.session.add(protocol)
        self.session.commit()
        return protocol

    def evaluate_for_paper_eligibility(self, protocol: models.Protocol) -> bool:
        if ProtocolStatus(protocol.status) != ProtocolStatus.RESEARCH_ONLY:
            raise ProtocolTransitionError(
                f"protocol {protocol.id} is {protocol.status}, not RESEARCH_ONLY; cannot evaluate"
            )
        if protocol.risk_score is None:
            raise ProtocolTransitionError(
                f"protocol {protocol.id} has no risk score yet; call update_evidence first"
            )
        if protocol.risk_score > self.risk_config.paper_eligible_max_risk_score:
            return False

        protocol.status = ProtocolStatus.PAPER_ELIGIBLE
        self.session.add(protocol)
        self.session.commit()
        return True

    def flag_for_review(self, protocol: models.Protocol, reason: str) -> models.Protocol:
        if ProtocolStatus(protocol.status) == ProtocolStatus.DISABLED:
            raise ProtocolTransitionError(f"protocol {protocol.id} is DISABLED; cannot flag for review")

        protocol.status = ProtocolStatus.REVIEW_REQUIRED
        self.session.add(protocol)
        self.session.add(
            models.AuditLog(
                actor="protocol_discovery_agent",
                action="PROTOCOL_FLAGGED_FOR_REVIEW",
                entity_type="protocol",
                entity_id=protocol.id,
                details={"reason": reason},
            )
        )
        self.session.commit()
        return protocol

    def clear_review(self, protocol: models.Protocol) -> models.Protocol:
        if ProtocolStatus(protocol.status) != ProtocolStatus.REVIEW_REQUIRED:
            raise ProtocolTransitionError(f"protocol {protocol.id} is not REVIEW_REQUIRED")

        protocol.status = ProtocolStatus.PAPER_ELIGIBLE
        self.session.add(protocol)
        self.session.commit()
        return protocol

    def disable(self, protocol: models.Protocol, reason: str) -> models.Protocol:
        protocol.status = ProtocolStatus.DISABLED
        self.session.add(protocol)
        self.session.add(
            models.AuditLog(
                actor="protocol_discovery_agent",
                action="PROTOCOL_DISABLED",
                entity_type="protocol",
                entity_id=protocol.id,
                details={"reason": reason},
            )
        )
        self.session.commit()
        return protocol
