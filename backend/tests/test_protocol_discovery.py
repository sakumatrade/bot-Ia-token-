from __future__ import annotations

import pytest

from broker_sakuma.config import ProtocolRiskScoreConfig
from broker_sakuma.core.enums import ProtocolStatus
from broker_sakuma.db import models
from broker_sakuma.engines.protocol_discovery import (
    ProtocolDiscoveryAgent,
    ProtocolTransitionError,
    compute_risk_score,
)


def test_register_protocol_starts_research_only(db_session):
    agent = ProtocolDiscoveryAgent(db_session, ProtocolRiskScoreConfig())
    protocol = agent.register_protocol("Raydium", blockchain="solana", category="DEX")
    assert protocol.status == ProtocolStatus.RESEARCH_ONLY


def test_registering_same_protocol_twice_is_idempotent(db_session):
    agent = ProtocolDiscoveryAgent(db_session, ProtocolRiskScoreConfig())
    p1 = agent.register_protocol("Raydium", blockchain="solana")
    p2 = agent.register_protocol("Raydium", blockchain="solana")
    assert p1.id == p2.id


def test_risk_score_rewards_audits_and_age_and_tvl(db_session):
    config = ProtocolRiskScoreConfig()
    bare = models.Protocol(name="Bare", blockchain="solana")
    evidenced = models.Protocol(
        name="Evidenced",
        blockchain="solana",
        audits=[{"firm": "X"}, {"firm": "Y"}],
        age_days=400,
        tvl_usd=2_000_000.0,
        incidents=[],
    )
    assert compute_risk_score(evidenced, config) < compute_risk_score(bare, config)


def test_risk_score_penalizes_incidents(db_session):
    config = ProtocolRiskScoreConfig()
    clean = models.Protocol(name="Clean", blockchain="solana")
    incident_prone = models.Protocol(name="Incidents", blockchain="solana", incidents=[{"date": "2025-01-01"}])
    assert compute_risk_score(incident_prone, config) > compute_risk_score(clean, config)


def test_risk_score_is_clamped_between_zero_and_hundred(db_session):
    config = ProtocolRiskScoreConfig()
    very_risky = models.Protocol(name="Risky", blockchain="solana", incidents=[{}] * 20)
    very_safe = models.Protocol(
        name="Safe", blockchain="solana", audits=[{}] * 10, age_days=100_000, tvl_usd=10_000_000_000.0
    )
    assert compute_risk_score(very_risky, config) == 100.0
    assert compute_risk_score(very_safe, config) == 0.0


def test_update_evidence_never_overwrites_unspecified_fields(db_session):
    agent = ProtocolDiscoveryAgent(db_session, ProtocolRiskScoreConfig())
    protocol = agent.register_protocol("Orca", blockchain="solana")
    agent.update_evidence(protocol, tvl_usd=500_000.0)
    assert protocol.tvl_usd == 500_000.0
    assert protocol.age_days is None  # never guessed at

    agent.update_evidence(protocol, age_days=30)
    assert protocol.tvl_usd == 500_000.0  # untouched by the second call
    assert protocol.age_days == 30


def test_evaluate_for_paper_eligibility_requires_a_risk_score_first(db_session):
    agent = ProtocolDiscoveryAgent(db_session, ProtocolRiskScoreConfig())
    protocol = agent.register_protocol("Orca", blockchain="solana")
    with pytest.raises(ProtocolTransitionError):
        agent.evaluate_for_paper_eligibility(protocol)


def test_evaluate_for_paper_eligibility_rejects_high_risk(db_session):
    config = ProtocolRiskScoreConfig(paper_eligible_max_risk_score=10.0)
    agent = ProtocolDiscoveryAgent(db_session, config)
    protocol = agent.register_protocol("Orca", blockchain="solana")
    agent.update_evidence(protocol, incidents=[{"date": "2025-01-01"}])  # pushes risk score up

    promoted = agent.evaluate_for_paper_eligibility(protocol)
    assert promoted is False
    assert protocol.status == ProtocolStatus.RESEARCH_ONLY


def test_evaluate_for_paper_eligibility_promotes_low_risk(db_session):
    config = ProtocolRiskScoreConfig(paper_eligible_max_risk_score=80.0)
    agent = ProtocolDiscoveryAgent(db_session, config)
    protocol = agent.register_protocol("Orca", blockchain="solana")
    agent.update_evidence(protocol, tvl_usd=2_000_000.0, age_days=500, audits=[{"firm": "X"}])

    promoted = agent.evaluate_for_paper_eligibility(protocol)
    assert promoted is True
    assert protocol.status == ProtocolStatus.PAPER_ELIGIBLE


def test_there_is_no_status_that_means_approved_for_live_trading():
    """Structural guarantee behind spec section 24's 'never jump straight
    from discovery to real operation': the enum simply has no such value."""

    all_status_values = {status.value for status in ProtocolStatus}
    forbidden = {"LIVE", "APPROVED", "ACTIVE", "TRADING_ENABLED"}
    assert not (all_status_values & forbidden)


def test_flag_for_review_and_clear(db_session):
    agent = ProtocolDiscoveryAgent(db_session, ProtocolRiskScoreConfig())
    protocol = agent.register_protocol("Orca", blockchain="solana")
    agent.update_evidence(protocol, tvl_usd=100.0)
    agent.evaluate_for_paper_eligibility(protocol)

    agent.flag_for_review(protocol, reason="unusual withdrawal pattern")
    assert protocol.status == ProtocolStatus.REVIEW_REQUIRED

    agent.clear_review(protocol)
    assert protocol.status == ProtocolStatus.PAPER_ELIGIBLE


def test_cannot_flag_disabled_protocol_for_review(db_session):
    agent = ProtocolDiscoveryAgent(db_session, ProtocolRiskScoreConfig())
    protocol = agent.register_protocol("Orca", blockchain="solana")
    agent.disable(protocol, reason="rug pull confirmed")

    with pytest.raises(ProtocolTransitionError):
        agent.flag_for_review(protocol, reason="too late")
