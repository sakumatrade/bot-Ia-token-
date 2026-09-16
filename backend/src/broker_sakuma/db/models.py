"""ORM models for every table required by spec section 45.

Design notes:
- All monetary columns are explicit ``*_usd`` floats for now (a future phase
  may move to fixed-point Decimal once real execution is wired up).
- ``audit_logs`` and ``post_mortems`` are append-only from the application
  layer: nothing in this codebase issues a DELETE against them.
- Foreign keys reference other tables by their string UUID primary key.
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from broker_sakuma.core.enums import (
    AlertLevel,
    BotLifecycleEventType,
    BotState,
    ExecutionMode,
    InfoClassification,
    InterestModel,
    LoanStatus,
    PositionStatus,
    ProtocolStatus,
    StrategyState,
    SystemState,
    TelegramRole,
    ThesisState,
    TradeSide,
    TransferStatus,
    WalletKind,
    WalletType,
)
from broker_sakuma.db.base import Base, IdMixin, TimestampMixin, UpdatedAtMixin


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(255))
    telegram_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    telegram_role: Mapped[Optional[TelegramRole]] = mapped_column(String(16), nullable=True)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)


class Wallet(Base, IdMixin, TimestampMixin):
    __tablename__ = "wallets"

    name: Mapped[str] = mapped_column(String(255))
    blockchain: Mapped[str] = mapped_column(String(64), default="solana")
    wallet_type: Mapped[WalletType] = mapped_column(String(32))
    kind: Mapped[WalletKind] = mapped_column(String(32), default=WalletKind.WATCH_ONLY)
    public_address: Mapped[str] = mapped_column(String(255))
    purpose: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_bot_id: Mapped[Optional[str]] = mapped_column(ForeignKey("bots.id"), nullable=True)


class Bot(Base, IdMixin, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "bots"

    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(32), default="1")
    parent_id: Mapped[Optional[str]] = mapped_column(ForeignKey("bots.id"), nullable=True)
    generation: Mapped[int] = mapped_column(Integer, default=0)
    strategy_id: Mapped[Optional[str]] = mapped_column(ForeignKey("strategies.id"), nullable=True)
    wallet_id: Mapped[Optional[str]] = mapped_column(ForeignKey("wallets.id"), nullable=True)
    state: Mapped[BotState] = mapped_column(String(32), default=BotState.CREATED)

    capital_operational_usd: Mapped[float] = mapped_column(Float, default=0.0)
    reserve_usd: Mapped[float] = mapped_column(Float, default=0.0)
    capital_borrowed_usd: Mapped[float] = mapped_column(Float, default=0.0)
    max_loss_usd: Mapped[float] = mapped_column(Float, default=5.0)
    cumulative_pnl_usd: Mapped[float] = mapped_column(Float, default=0.0)
    peak_equity_usd: Mapped[float] = mapped_column(Float, default=0.0)
    drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)

    trades_count: Mapped[int] = mapped_column(Integer, default=0)
    theses_tested_count: Mapped[int] = mapped_column(Integer, default=0)

    died_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)


class BotLineage(Base, IdMixin, TimestampMixin):
    __tablename__ = "bot_lineage"

    bot_id: Mapped[str] = mapped_column(ForeignKey("bots.id"))
    parent_id: Mapped[Optional[str]] = mapped_column(ForeignKey("bots.id"), nullable=True)
    generation: Mapped[int] = mapped_column(Integer, default=0)
    relationship_type: Mapped[str] = mapped_column(String(32), default="child")  # child | resurrection
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    previous_failure: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correction: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class BotLifecycleEvent(Base, IdMixin, TimestampMixin):
    __tablename__ = "bot_lifecycle_events"

    bot_id: Mapped[str] = mapped_column(ForeignKey("bots.id"))
    event_type: Mapped[BotLifecycleEventType] = mapped_column(String(32))
    from_state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    to_state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Creator(Base, IdMixin, TimestampMixin):
    __tablename__ = "creators"

    blockchain: Mapped[str] = mapped_column(String(64), default="solana")
    address: Mapped[str] = mapped_column(String(255))
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    risk_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Token(Base, IdMixin, TimestampMixin):
    __tablename__ = "tokens"

    blockchain: Mapped[str] = mapped_column(String(64), default="solana")
    mint_address: Mapped[str] = mapped_column(String(255))
    symbol: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    creator_id: Mapped[Optional[str]] = mapped_column(ForeignKey("creators.id"), nullable=True)
    launch_protocol: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    token_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Protocol(Base, IdMixin, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "protocols"

    name: Mapped[str] = mapped_column(String(255))
    blockchain: Mapped[str] = mapped_column(String(64))
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    docs_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[ProtocolStatus] = mapped_column(String(32), default=ProtocolStatus.RESEARCH_ONLY)
    tvl_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    volume_24h_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    age_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    audits: Mapped[list[Any]] = mapped_column(JSON, default=list)
    incidents: Mapped[list[Any]] = mapped_column(JSON, default=list)
    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class Opportunity(Base, IdMixin, TimestampMixin):
    __tablename__ = "opportunities"

    protocol_id: Mapped[Optional[str]] = mapped_column(ForeignKey("protocols.id"), nullable=True)
    token_id: Mapped[Optional[str]] = mapped_column(ForeignKey("tokens.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(64))
    classification: Mapped[InfoClassification] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="RESEARCH")
    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Strategy(Base, IdMixin, TimestampMixin):
    __tablename__ = "strategies"

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_bot_id: Mapped[Optional[str]] = mapped_column(ForeignKey("bots.id"), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class StrategyVersion(Base, IdMixin, TimestampMixin):
    __tablename__ = "strategy_versions"

    strategy_id: Mapped[str] = mapped_column(ForeignKey("strategies.id"))
    version: Mapped[str] = mapped_column(String(32))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    state: Mapped[StrategyState] = mapped_column(String(32), default=StrategyState.RESEARCH)

    __table_args__ = (UniqueConstraint("strategy_id", "version", name="uq_strategy_version"),)


class Backtest(Base, IdMixin, TimestampMixin):
    __tablename__ = "backtests"

    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"))
    dataset_split: Mapped[str] = mapped_column(String(16))  # TRAIN | VALIDATION | TEST
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PaperTrade(Base, IdMixin, TimestampMixin):
    __tablename__ = "paper_trades"

    bot_id: Mapped[str] = mapped_column(ForeignKey("bots.id"))
    token_id: Mapped[Optional[str]] = mapped_column(ForeignKey("tokens.id"), nullable=True)
    side: Mapped[TradeSide] = mapped_column(String(8))
    price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[float] = mapped_column(Float)
    fee_usd: Mapped[float] = mapped_column(Float, default=0.0)
    slippage_pct: Mapped[float] = mapped_column(Float, default=0.0)
    simulated_pnl_usd: Mapped[float] = mapped_column(Float, default=0.0)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    executed_at: Mapped[datetime]


class Trade(Base, IdMixin, TimestampMixin):
    """Real (or would-be real) trades. ``mode`` is always PAPER until live
    trading is explicitly enabled (spec sections 4, 61)."""

    __tablename__ = "trades"

    bot_id: Mapped[str] = mapped_column(ForeignKey("bots.id"))
    position_id: Mapped[Optional[str]] = mapped_column(ForeignKey("positions.id"), nullable=True)
    token_id: Mapped[Optional[str]] = mapped_column(ForeignKey("tokens.id"), nullable=True)
    side: Mapped[TradeSide] = mapped_column(String(8))
    mode: Mapped[ExecutionMode] = mapped_column(String(8), default=ExecutionMode.PAPER)
    price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[float] = mapped_column(Float)
    fee_usd: Mapped[float] = mapped_column(Float, default=0.0)
    slippage_pct: Mapped[float] = mapped_column(Float, default=0.0)
    pnl_usd: Mapped[float] = mapped_column(Float, default=0.0)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    executed_at: Mapped[datetime]


class Position(Base, IdMixin, TimestampMixin):
    __tablename__ = "positions"

    bot_id: Mapped[str] = mapped_column(ForeignKey("bots.id"))
    token_id: Mapped[str] = mapped_column(ForeignKey("tokens.id"))
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    avg_entry_price: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[PositionStatus] = mapped_column(String(16), default=PositionStatus.OPEN)
    closed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)


class Thesis(Base, IdMixin, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "theses"

    bot_id: Mapped[str] = mapped_column(ForeignKey("bots.id"))
    strategy_version_id: Mapped[Optional[str]] = mapped_column(ForeignKey("strategy_versions.id"), nullable=True)
    state: Mapped[ThesisState] = mapped_column(String(32), default=ThesisState.RESEARCH)
    initial_capital_usd: Mapped[float] = mapped_column(Float, default=5.0)
    current_capital_usd: Mapped[float] = mapped_column(Float, default=5.0)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class LearningEvent(Base, IdMixin, TimestampMixin):
    __tablename__ = "learning_events"

    source_bot_id: Mapped[Optional[str]] = mapped_column(ForeignKey("bots.id"), nullable=True)
    kind: Mapped[InfoClassification] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    related_thesis_id: Mapped[Optional[str]] = mapped_column(ForeignKey("theses.id"), nullable=True)


class RiskEvent(Base, IdMixin, TimestampMixin):
    __tablename__ = "risk_events"

    bot_id: Mapped[Optional[str]] = mapped_column(ForeignKey("bots.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16), default="INFO")
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Treasury(Base, IdMixin, UpdatedAtMixin):
    __tablename__ = "treasury"

    owner: Mapped[str] = mapped_column(String(64), default="mother", unique=True)
    total_capital_usd: Mapped[float] = mapped_column(Float, default=0.0)
    available_to_loan_usd: Mapped[float] = mapped_column(Float, default=0.0)


class Transfer(Base, IdMixin, TimestampMixin):
    __tablename__ = "transfers"

    from_wallet_id: Mapped[Optional[str]] = mapped_column(ForeignKey("wallets.id"), nullable=True)
    to_wallet_id: Mapped[Optional[str]] = mapped_column(ForeignKey("wallets.id"), nullable=True)
    amount_usd: Mapped[float] = mapped_column(Float)
    purpose: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[TransferStatus] = mapped_column(String(16), default=TransferStatus.PENDING)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)


class Alert(Base, IdMixin, TimestampMixin):
    __tablename__ = "alerts"

    level: Mapped[AlertLevel] = mapped_column(String(16), default=AlertLevel.INFO)
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditLog(Base, IdMixin, TimestampMixin):
    """Append-only. Nothing in the codebase may DELETE from this table."""

    __tablename__ = "audit_logs"

    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(128))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class SystemEvent(Base, IdMixin, TimestampMixin):
    __tablename__ = "system_events"

    event_type: Mapped[str] = mapped_column(String(64))
    state: Mapped[SystemState] = mapped_column(String(32))
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class BotLoan(Base, IdMixin, TimestampMixin):
    __tablename__ = "bot_loans"

    loan_id: Mapped[str] = mapped_column(String(64), unique=True)
    bot_id: Mapped[str] = mapped_column(ForeignKey("bots.id"))
    mother_id: Mapped[str] = mapped_column(ForeignKey("bots.id"))
    principal_usd: Mapped[float] = mapped_column(Float)
    purpose: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    thesis_id: Mapped[Optional[str]] = mapped_column(ForeignKey("theses.id"), nullable=True)
    term_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    interest_model: Mapped[InterestModel] = mapped_column(String(16))
    interest_rate: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[LoanStatus] = mapped_column(String(16), default=LoanStatus.ACTIVE)
    remaining_balance_usd: Mapped[float] = mapped_column(Float, default=0.0)


class LoanPayment(Base, IdMixin, TimestampMixin):
    __tablename__ = "loan_payments"

    loan_id: Mapped[str] = mapped_column(ForeignKey("bot_loans.id"))
    amount_usd: Mapped[float] = mapped_column(Float)
    principal_component_usd: Mapped[float] = mapped_column(Float, default=0.0)
    interest_component_usd: Mapped[float] = mapped_column(Float, default=0.0)
    remaining_balance_usd: Mapped[float] = mapped_column(Float, default=0.0)


class FundingEvent(Base, IdMixin, TimestampMixin):
    __tablename__ = "funding_events"

    bot_id: Mapped[str] = mapped_column(ForeignKey("bots.id"))
    mother_id: Mapped[str] = mapped_column(ForeignKey("bots.id"))
    amount_usd: Mapped[float] = mapped_column(Float)
    funding_type: Mapped[str] = mapped_column(String(32))  # initial_thesis | escalation | loan
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Reserve(Base, IdMixin, UpdatedAtMixin):
    __tablename__ = "reserves"

    bot_id: Mapped[Optional[str]] = mapped_column(ForeignKey("bots.id"), nullable=True, unique=True)
    balance_usd: Mapped[float] = mapped_column(Float, default=0.0)


class PostMortem(Base, IdMixin, TimestampMixin):
    """Append-only record of why a bot died. Never deleted (spec section 13)."""

    __tablename__ = "post_mortems"

    bot_id: Mapped[str] = mapped_column(ForeignKey("bots.id"))
    thesis_id: Mapped[Optional[str]] = mapped_column(ForeignKey("theses.id"), nullable=True)
    strategy_version_id: Mapped[Optional[str]] = mapped_column(ForeignKey("strategy_versions.id"), nullable=True)
    token_id: Mapped[Optional[str]] = mapped_column(ForeignKey("tokens.id"), nullable=True)
    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    slippage_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    liquidity_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    market_condition: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    probable_cause: Mapped[str] = mapped_column(Text)
    confirmed_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failed_hypothesis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rule_that_should_have_prevented: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class CollectiveMemory(Base, IdMixin, TimestampMixin):
    __tablename__ = "collective_memory"

    source_bot_id: Mapped[str] = mapped_column(ForeignKey("bots.id"))
    post_mortem_id: Mapped[Optional[str]] = mapped_column(ForeignKey("post_mortems.id"), nullable=True)
    kind: Mapped[InfoClassification] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[list[Any]] = mapped_column(JSON, default=list)


class DailySettlement(Base, IdMixin, TimestampMixin):
    __tablename__ = "daily_settlements"

    bot_id: Mapped[str] = mapped_column(ForeignKey("bots.id"))
    settlement_date: Mapped[date] = mapped_column(Date)
    gross_result_usd: Mapped[float] = mapped_column(Float, default=0.0)
    fees_usd: Mapped[float] = mapped_column(Float, default=0.0)
    interest_usd: Mapped[float] = mapped_column(Float, default=0.0)
    loan_repayment_usd: Mapped[float] = mapped_column(Float, default=0.0)
    returned_to_mother_usd: Mapped[float] = mapped_column(Float, default=0.0)
    retained_operational_usd: Mapped[float] = mapped_column(Float, default=0.0)
    reserve_contribution_usd: Mapped[float] = mapped_column(Float, default=0.0)
    final_equity_usd: Mapped[float] = mapped_column(Float, default=0.0)

    __table_args__ = (UniqueConstraint("bot_id", "settlement_date", name="uq_bot_settlement_date"),)


class ResearchReport(Base, IdMixin, TimestampMixin):
    __tablename__ = "research_reports"

    protocol_id: Mapped[Optional[str]] = mapped_column(ForeignKey("protocols.id"), nullable=True)
    opportunity_id: Mapped[Optional[str]] = mapped_column(ForeignKey("opportunities.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="RESEARCH_ONLY")
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
