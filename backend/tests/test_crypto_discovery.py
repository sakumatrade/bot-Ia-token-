from __future__ import annotations

from broker_sakuma.config import ProtocolRiskScoreConfig
from broker_sakuma.core.enums import BotState, InfoClassification, OpportunityCategory
from broker_sakuma.db import models
from broker_sakuma.engines.crypto_discovery import CryptoDiscoveryEngine, CryptoResearchLab, RevenueDiscoveryEngine
from broker_sakuma.engines.learning_engine import LearningEngine
from broker_sakuma.engines.protocol_discovery import ProtocolDiscoveryAgent


def test_register_opportunity_defaults_to_research_status(db_session):
    engine = CryptoDiscoveryEngine(db_session)
    opp = engine.register_opportunity(
        source="scanner", classification=InfoClassification.DATA, category=OpportunityCategory.ARBITRAGE
    )
    assert opp.status == "RESEARCH"
    assert opp.evidence["category"] == "ARBITRAGE"


def test_mark_ignored_records_reason(db_session):
    engine = CryptoDiscoveryEngine(db_session)
    opp = engine.register_opportunity(source="scanner", classification=InfoClassification.DATA)
    engine.mark_ignored(opp, reason="risk above threshold")
    assert opp.status == "IGNORE"
    assert opp.evidence["ignore_reason"] == "risk above threshold"


def test_revenue_discovery_creates_hypothesis_and_opportunity(db_session):
    bot = models.Bot(name="Son 400", state=BotState.ACTIVE)
    db_session.add(bot)
    db_session.commit()

    discovery = CryptoDiscoveryEngine(db_session)
    learning = LearningEngine(db_session)
    revenue = RevenueDiscoveryEngine(db_session, discovery, learning)

    event, opportunity = revenue.propose_revenue_idea(
        bot.id, "MEV rebate program", "Some validators share MEV rebates with active stakers"
    )

    assert event.kind == InfoClassification.HYPOTHESIS
    assert opportunity.classification == InfoClassification.HYPOTHESIS
    assert opportunity.source == "revenue_discovery"


def test_research_lab_board_groups_by_status(db_session):
    agent = ProtocolDiscoveryAgent(db_session, ProtocolRiskScoreConfig(paper_eligible_max_risk_score=80.0))
    p1 = agent.register_protocol("Raydium", blockchain="solana")
    p2 = agent.register_protocol("Orca", blockchain="solana")
    agent.update_evidence(p2, tvl_usd=2_000_000.0, age_days=500)
    agent.evaluate_for_paper_eligibility(p2)
    p3 = agent.register_protocol("Sketchy DEX", blockchain="solana")
    agent.disable(p3, reason="unaudited, anonymous team")

    lab = CryptoResearchLab(db_session)
    board = lab.board()

    assert p1.name in [p.name for p in board["RESEARCH_ONLY"]]
    assert p2.name in [p.name for p in board["PAPER_ELIGIBLE"]]
    assert p3.name in [p.name for p in board["DISABLED"]]
    assert board["REVIEW_REQUIRED"] == []
