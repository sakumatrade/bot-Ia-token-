"""Central, explicit configuration for DominusBot.

Every financially meaningful policy (risk limits, loan exposure, settlement
splits, growth ladders) lives here as an explicit, documented, overridable
setting. Nothing that moves money is allowed to be a hardcoded constant
buried inside engine logic (spec sections 19, 57, 62).

All settings can be overridden via environment variables (prefix
``BROKER_SAKUMA_``) or a ``.env`` file. Defaults are conservative and keep
the system in simulation / paper-trading mode.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from broker_sakuma.core.enums import InterestModel


class Environment(str, Enum):
    SIMULATION = "simulation"
    PRODUCTION = "production"


class DatabaseConfig(BaseModel):
    url: str = "sqlite:///./broker_sakuma.db"
    echo: bool = False


class RedisConfig(BaseModel):
    url: str = "redis://localhost:6379/0"


class RiskPolicyConfig(BaseModel):
    """Global risk limits. No order may bypass the Risk Engine (section 28)."""

    max_position_usd: float = 5.0
    max_daily_loss_usd: float = 50.0
    max_drawdown_pct: float = 0.25
    max_slippage_pct: float = 0.05
    min_liquidity_usd: float = 1000.0
    max_trades_per_day: int = 20
    max_consecutive_losses: int = 5
    min_wallet_balance_usd: float = 5.0


class MaximumLossPolicyConfig(BaseModel):
    """Per-bot loss ceiling that forces DEAD state (spec section 12)."""

    per_bot_max_loss_usd: float = 5.0
    per_bot_max_loss_pct_of_capital: float | None = 1.0


class ThesisPolicyConfig(BaseModel):
    """The $5 rule (spec section 10) and the escalation ladder (section 11)."""

    initial_test_capital_usd: float = 5.0
    escalation_ladder_usd: list[float] = Field(
        default_factory=lambda: [5.0, 10.0, 25.0, 50.0, 100.0]
    )
    min_operations_for_validation: int = 20
    max_drawdown_pct_for_validation: float = 0.20


class LoanPolicyConfig(BaseModel):
    """Mother Bot internal treasury lending limits (spec section 17)."""

    mother_max_total_loan_pct_of_treasury: float = 0.20
    default_interest_model: InterestModel = InterestModel.PROFIT_SHARE
    fixed_interest_rate: float = 0.02
    profit_share_rate: float = 0.10
    hybrid_fixed_component: float = 0.01
    hybrid_profit_share_component: float = 0.05


class SettlementPolicyConfig(BaseModel):
    """Daily settlement split (spec section 19). Percentages are explicit."""

    operational_capital_retention_pct: float = 0.50
    reserve_contribution_pct: float = 0.20
    returned_to_mother_pct: float = 0.30


class GrowthPolicyConfig(BaseModel):
    """Bot growth / spawning limits (spec section 63)."""

    max_bots: int = 50
    max_generations: int = 5
    minimum_capital_usd: float = 5.0
    minimum_reserve_usd: float = 25.0
    max_descendant_funding_usd: float = 100.0
    funding_frequency_days: int = 7
    max_mother_exposure_pct: float = 0.20


class TelegramConfig(BaseModel):
    enabled: bool = False
    bot_token: str | None = None
    owner_user_id: str | None = None


class TradingConfig(BaseModel):
    """Live trading is disabled until explicitly, manually enabled per section 4/61."""

    live_trading_enabled: bool = False


class AutoTradingConfig(BaseModel):
    """Autonomous PAPER-trading loop: once enabled, active bots watch and
    trade against synthetic mock launches on their own, with no manual
    `/api/system/run-cycle` call needed per trade. This is entirely
    separate from — and can never enable — real/live trading:
    `TradingConfig.live_trading_enabled` stays False regardless of this
    flag, and this loop only ever executes through the same
    `PaperExecutor` every other phase uses.
    """

    enabled: bool = False
    interval_seconds: float = 10.0
    launches_per_cycle: int = 1
    position_fraction_of_capital: float = 0.5


class ProtocolRiskScoreConfig(BaseModel):
    """Protocol Risk Score weights (spec section 24). 0 = safest, 100 =
    riskiest. Deliberately scored only from evidence the schema actually
    collects (TVL, volume, age, audit count, incident count) — it never
    fabricates a concentration/smart-contract sub-score from data we don't
    have (see docs/PHASES.md for why those are future work, not guesses).
    """

    baseline_score: float = 50.0
    max_audit_reduction: float = 20.0
    audit_score_reduction_per_audit: float = 10.0
    incident_score_penalty_per_incident: float = 15.0
    age_days_for_full_credit: int = 365
    max_age_score_reduction: float = 15.0
    tvl_usd_for_full_credit: float = 1_000_000.0
    max_tvl_score_reduction: float = 15.0
    paper_eligible_max_risk_score: float = 60.0


class LocalAPIConfig(BaseModel):
    """Local API (spec section 38). No default API key is baked in: an
    unset key means the dependency rejects every request rather than
    silently running an unauthenticated local API.

    ``read_only_api_key`` is a second, optional, weaker key meant to be
    handed out to people who only watch the bot (e.g. someone learning by
    observing it) — it authenticates GET requests exactly like the main
    key, but every state-changing request is rejected outright
    (``api/deps.py::require_api_key``), never silently ignored. There is
    still no deposit, no wallet, and no way for a viewer to change
    anything — this only ever controls whether a browser can *see* the
    simulated dashboard, never money.
    """

    api_key: str | None = None
    read_only_api_key: str | None = None
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1", "http://localhost"]
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BROKER_SAKUMA_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    environment: Environment = Environment.SIMULATION
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    risk: RiskPolicyConfig = Field(default_factory=RiskPolicyConfig)
    max_loss: MaximumLossPolicyConfig = Field(default_factory=MaximumLossPolicyConfig)
    thesis: ThesisPolicyConfig = Field(default_factory=ThesisPolicyConfig)
    loan: LoanPolicyConfig = Field(default_factory=LoanPolicyConfig)
    settlement: SettlementPolicyConfig = Field(default_factory=SettlementPolicyConfig)
    growth: GrowthPolicyConfig = Field(default_factory=GrowthPolicyConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    auto_trading: AutoTradingConfig = Field(default_factory=AutoTradingConfig)
    local_api: LocalAPIConfig = Field(default_factory=LocalAPIConfig)
    protocol_risk_score: ProtocolRiskScoreConfig = Field(default_factory=ProtocolRiskScoreConfig)


def get_settings() -> Settings:
    """Factory (not a cached singleton) so tests can construct isolated settings."""

    return Settings()
