"""Response models for the Local API. Field names are snake_case to match
the macOS app's ``JSONDecoder.keyDecodingStrategy = .convertFromSnakeCase``
(see macapp/Sources/BrokerSakuma/DashboardModels.swift).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StatusResponse(BaseModel):
    system_state: str
    environment: str
    live_trading_enabled: bool


class DashboardResponse(BaseModel):
    system_state: str
    capital_operational_usd: float
    reserve_usd: float
    capital_borrowed_usd: float
    daily_pnl_usd: float
    total_pnl_usd: float
    active_bots: int
    dead_bots: int
    resurrected_bots: int
    new_theses: int
    approved_theses: int
    theses_in_research: int
    simulated_trades: int
    success_rate: float
    max_drawdown_pct: float
    unacknowledged_alerts: int


class BotSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    version: str
    state: str
    generation: int
    parent_id: str | None
    capital_operational_usd: float
    reserve_usd: float
    capital_borrowed_usd: float
    cumulative_pnl_usd: float
    drawdown_pct: float
    trades_count: int
    theses_tested_count: int


class AlertSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    level: str
    title: str
    message: str | None
    source: str | None
    acknowledged: bool
    created_at: datetime


class ProtocolSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    blockchain: str
    category: str | None
    status: str
    risk_score: float | None
    tvl_usd: float | None
    volume_24h_usd: float | None
    age_days: int | None
    updated_at: datetime


class OpportunitySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    classification: str
    status: str
    risk_score: float | None
    description: str | None
    created_at: datetime


class PaperTradeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    bot_id: str
    token_id: str | None
    side: str
    price: float
    quantity: float
    fee_usd: float
    slippage_pct: float
    simulated_pnl_usd: float
    executed_at: datetime


class StrategySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    category: str | None
    owner_bot_id: str | None


class ResearchReportSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    status: str
    summary: str | None
    created_at: datetime


class BotLoanSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    loan_id: str
    bot_id: str
    mother_id: str
    principal_usd: float
    interest_model: str
    interest_rate: float
    status: str
    remaining_balance_usd: float


class ReserveSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    bot_id: str | None
    balance_usd: float


class WalletSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    blockchain: str
    wallet_type: str
    kind: str
    public_address: str
    purpose: str | None
    is_active: bool


class AddWalletRequest(BaseModel):
    """Watch-only only: there is no field for a private key, seed phrase,
    or mnemonic here, and the route handler enforces ``kind=WATCH_ONLY``
    unconditionally — no real signer exists in this backend (see
    ``engines/signer.py``), so nothing here could ever pretend to add a
    signing-capable wallet.
    """

    name: str
    blockchain: str = "solana"
    wallet_type: str
    public_address: str
    purpose: str | None = None


class CreateMotherBotRequest(BaseModel):
    """Simulated starting capital only — a plain number in this system's
    own database, never a blockchain balance or a real wallet (see
    ``docs/ARCHITECTURE.md#security``: there is no code path anywhere in
    this backend that can move real funds)."""

    name: str = "Mother Bot"
    initial_capital_usd: float = 1000.0


class SpawnSonRequest(BaseModel):
    parent_id: str
    name: str | None = None


class ActivateBotResponse(BaseModel):
    bot: BotSummary
    thesis_id: str
    initial_capital_usd: float


class GrowthResponse(BaseModel):
    max_bots: int
    max_generations: int
    max_mother_exposure_pct: float
    total_bots: int
    bots_by_generation: dict[int, int]


class SystemActionResponse(BaseModel):
    system_state: str


class RunCycleResponse(BaseModel):
    """One tick of the autonomous PAPER-trading loop — simulated only,
    against synthetic mock launches (see
    ``engines/autonomous_trading_cycle.py``)."""

    decisions_evaluated: int
    trades_executed: int
    bots_died: list[str]


class KillSwitchRequest(BaseModel):
    reason: str
