"""PumpFunMonitor (spec section 22): the discovery/triage pipeline.

    New Launch -> Creator Analysis -> Token Analysis -> Liquidity Analysis
    -> Risk Analysis -> Strategy -> Risk Engine -> BUY/SELL/WATCH/IGNORE

This module implements the pipeline up through the risk-analysis triage,
producing only WATCH or IGNORE. It deliberately stops there: BUY/SELL is
only ever the outcome of a Strategy proposing a concrete, priced order
that then passes through the *existing*, already-tested
``engines.risk_engine.RiskEngine`` and ``paper.paper_executor.PaperExecutor``
(spec sections 3, 28). Wiring this monitor directly to a BUY/SELL decision
without a real strategy and a real order would be simulating an
integration that isn't actually there yet — exactly what the spec forbids
(section 61: "nunca simular uma integração real como se fosse funcional").
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from broker_sakuma.adapters.pumpfun.provider import LaunchEvent, PumpFunProvider
from broker_sakuma.config import RiskPolicyConfig
from broker_sakuma.core.enums import InfoClassification, OpportunityCategory
from broker_sakuma.db import models
from broker_sakuma.engines.crypto_discovery import CryptoDiscoveryEngine


@dataclass
class CreatorAnalysis:
    creator_id: str
    is_known_bad_actor: bool
    prior_launches_count: int


@dataclass
class LiquidityAnalysis:
    liquidity_usd: float
    meets_minimum: bool


@dataclass
class RiskAnalysis:
    risk_score: float  # 0 (safest) to 100 (riskiest)
    violated_rules: list[str] = field(default_factory=list)


@dataclass
class PipelineDecision:
    launch: LaunchEvent
    token_id: str
    creator_analysis: CreatorAnalysis
    liquidity_analysis: LiquidityAnalysis
    risk_analysis: RiskAnalysis
    action: str  # WATCH | IGNORE — never BUY/SELL from this pipeline alone
    reason: str


class PumpFunMonitor:
    def __init__(self, session: Session, provider: PumpFunProvider, risk_config: RiskPolicyConfig):
        self.session = session
        self.provider = provider
        self.risk_config = risk_config
        self.discovery_engine = CryptoDiscoveryEngine(session)

    def poll(self) -> list[PipelineDecision]:
        return [self.evaluate(launch) for launch in self.provider.fetch_new_launches()]

    def evaluate(self, launch: LaunchEvent) -> PipelineDecision:
        creator_analysis = self._analyze_creator(launch)
        token = self._register_token(launch, creator_analysis.creator_id)
        liquidity_analysis = self._analyze_liquidity(launch)
        risk_analysis = self._analyze_risk(creator_analysis, liquidity_analysis)
        action, reason = self._decide(creator_analysis, liquidity_analysis, risk_analysis)

        self.discovery_engine.register_opportunity(
            source="pumpfun_monitor",
            classification=InfoClassification.DATA,
            category=OpportunityCategory.LAUNCHPAD,
            token_id=token.id,
            risk_score=risk_analysis.risk_score,
            description=f"{launch.symbol} ({launch.name}) — {action}: {reason}",
            evidence={
                "liquidity_usd": liquidity_analysis.liquidity_usd,
                "creator_prior_launches": creator_analysis.prior_launches_count,
                "violated_rules": risk_analysis.violated_rules,
            },
        )

        return PipelineDecision(
            launch=launch,
            token_id=token.id,
            creator_analysis=creator_analysis,
            liquidity_analysis=liquidity_analysis,
            risk_analysis=risk_analysis,
            action=action,
            reason=reason,
        )

    def _analyze_creator(self, launch: LaunchEvent) -> CreatorAnalysis:
        creator = self.session.execute(
            select(models.Creator).where(
                models.Creator.address == launch.creator_address, models.Creator.blockchain == launch.blockchain
            )
        ).scalar_one_or_none()
        if creator is None:
            creator = models.Creator(blockchain=launch.blockchain, address=launch.creator_address)
            self.session.add(creator)
            self.session.commit()

        prior_launches_count = self.session.execute(
            select(func.count(models.Token.id)).where(models.Token.creator_id == creator.id)
        ).scalar_one()

        return CreatorAnalysis(
            creator_id=creator.id,
            is_known_bad_actor=bool(creator.risk_notes),
            prior_launches_count=prior_launches_count,
        )

    def _register_token(self, launch: LaunchEvent, creator_id: str) -> models.Token:
        existing = self.session.execute(
            select(models.Token).where(
                models.Token.mint_address == launch.mint_address, models.Token.blockchain == launch.blockchain
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        token = models.Token(
            blockchain=launch.blockchain,
            mint_address=launch.mint_address,
            symbol=launch.symbol,
            name=launch.name,
            creator_id=creator_id,
            launch_protocol="pumpfun",
            token_metadata=launch.metadata,
        )
        self.session.add(token)
        self.session.commit()
        return token

    def _analyze_liquidity(self, launch: LaunchEvent) -> LiquidityAnalysis:
        liquidity_usd = launch.initial_liquidity_usd or 0.0
        return LiquidityAnalysis(
            liquidity_usd=liquidity_usd,
            meets_minimum=liquidity_usd >= self.risk_config.min_liquidity_usd,
        )

    def _analyze_risk(self, creator: CreatorAnalysis, liquidity: LiquidityAnalysis) -> RiskAnalysis:
        violated: list[str] = []
        score = 50.0

        if creator.is_known_bad_actor:
            violated.append("creator_flagged")
            score += 40.0
        if creator.prior_launches_count > 10:
            violated.append("creator_high_launch_velocity")
            score += 10.0
        if not liquidity.meets_minimum:
            violated.append("liquidity_below_minimum")
            score += 20.0

        return RiskAnalysis(risk_score=max(0.0, min(100.0, score)), violated_rules=violated)

    def _decide(
        self, creator: CreatorAnalysis, liquidity: LiquidityAnalysis, risk: RiskAnalysis
    ) -> tuple[str, str]:
        if creator.is_known_bad_actor:
            return "IGNORE", "creator previously flagged as a bad actor"
        if not liquidity.meets_minimum:
            return "IGNORE", (
                f"liquidity ${liquidity.liquidity_usd:.2f} below configured minimum "
                f"${self.risk_config.min_liquidity_usd:.2f}"
            )
        if risk.violated_rules:
            return "WATCH", f"passes minimum bar but flagged: {', '.join(risk.violated_rules)}"
        return "WATCH", "passes initial filters; awaiting a strategy to propose a concrete order"
