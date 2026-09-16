"""Domain enums shared by the whole backend.

These are the vocabulary of the system. They are referenced directly by the
spec (see docs/ARCHITECTURE.md) and must not be redefined ad-hoc elsewhere.
"""

from __future__ import annotations

import enum


class SystemState(str, enum.Enum):
    """Global system state shown on the dashboard (spec section 6)."""

    ONLINE = "ONLINE"
    PAUSED = "PAUSED"
    SAFE_HALT = "SAFE_HALT"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class BotState(str, enum.Enum):
    """Lifecycle states of a bot (spec section 64)."""

    CREATED = "CREATED"
    RESEARCHING = "RESEARCHING"
    BACKTESTING = "BACKTESTING"
    PAPER = "PAPER"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    REVIEW = "REVIEW"
    DEAD = "DEAD"
    RESURRECTING = "RESURRECTING"
    DISABLED = "DISABLED"
    SAFE_HALT = "SAFE_HALT"


class ThesisState(str, enum.Enum):
    """States of the $5-rule ThesisEngine (spec section 10)."""

    RESEARCH = "RESEARCH"
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    INITIAL_TEST = "INITIAL_TEST"
    VALIDATION = "VALIDATION"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    DISABLED = "DISABLED"


class StrategyState(str, enum.Enum):
    """States of a strategy version through backtesting (spec section 27)."""

    RESEARCH = "RESEARCH"
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    DISABLED = "DISABLED"


class InfoClassification(str, enum.Enum):
    """Classification bots must attach to shared information (spec section 9).

    A hypothesis must never be treated as a fact.
    """

    FACT = "FACT"
    DATA = "DATA"
    HYPOTHESIS = "HYPOTHESIS"
    SIMULATION = "SIMULATION"
    REAL_RESULT = "REAL_RESULT"
    AGENT_OPINION = "AGENT_OPINION"


class ProtocolStatus(str, enum.Enum):
    """Research Lab protocol status (spec section 24). Never skips to live."""

    RESEARCH_ONLY = "RESEARCH_ONLY"
    PAPER_ELIGIBLE = "PAPER_ELIGIBLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    DISABLED = "DISABLED"


class DatasetSplit(str, enum.Enum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST = "TEST"


class TradeSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class ExecutionMode(str, enum.Enum):
    """Only PAPER is enabled until live trading is explicitly approved."""

    PAPER = "PAPER"
    LIVE = "LIVE"


class PositionStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class WalletType(str, enum.Enum):
    """Wallet roles (spec section 32)."""

    MOTHER_WALLET = "MOTHER_WALLET"
    BOT_WALLET = "BOT_WALLET"
    RECEIVING_WALLET = "RECEIVING_WALLET"
    RESERVE_WALLET = "RESERVE_WALLET"


class WalletKind(str, enum.Enum):
    """Custody kind (spec section 33): a watch-only wallet never signs."""

    WATCH_ONLY = "WATCH_ONLY"
    SIGNING = "SIGNING"


class LoanStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PAID = "PAID"
    DEFAULTED = "DEFAULTED"
    CANCELLED = "CANCELLED"


class InterestModel(str, enum.Enum):
    """spec section 18."""

    FIXED = "FIXED"
    PROFIT_SHARE = "PROFIT_SHARE"
    HYBRID = "HYBRID"


class TransferStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class AlertLevel(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class TelegramRole(str, enum.Enum):
    """spec section 35."""

    VIEWER = "VIEWER"
    OPERATOR = "OPERATOR"
    OWNER = "OWNER"


class OpportunityCategory(str, enum.Enum):
    """spec section 23: categories CryptoDiscoveryEngine researches.
    Research only — none of these imply execution."""

    DEX = "DEX"
    DEFI = "DEFI"
    ARBITRAGE = "ARBITRAGE"
    STAKING = "STAKING"
    LENDING = "LENDING"
    LIQUIDITY_POOL = "LIQUIDITY_POOL"
    LAUNCHPAD = "LAUNCHPAD"
    YIELD = "YIELD"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    CROSS_CHAIN = "CROSS_CHAIN"
    OTHER = "OTHER"


class TelegramCommand(str, enum.Enum):
    """spec section 36. Fixed, closed set — the dispatcher in
    TelegramControlService only ever looks up one of these; there is no
    code path that runs an arbitrary string as a command."""

    STATUS = "status"
    PAUSE = "pause"
    RESUME = "resume"
    BOTS = "bots"
    PROFIT = "profit"
    ALERTS = "alerts"
    RESEARCH = "research"
    WALLETS = "wallets"
    OPPORTUNITIES = "opportunities"
    LOGS = "logs"
    KILL = "kill"
    DEATHS = "deaths"
    RESURRECTIONS = "resurrections"
    LOANS = "loans"
    RESERVES = "reserves"
    GROWTH = "growth"
    DAILY = "daily"


class BotLifecycleEventType(str, enum.Enum):
    CREATED = "CREATED"
    STATE_CHANGE = "STATE_CHANGE"
    FUNDED = "FUNDED"
    THESIS_STARTED = "THESIS_STARTED"
    DEAD = "DEAD"
    POST_MORTEM_CREATED = "POST_MORTEM_CREATED"
    RESURRECTED = "RESURRECTED"
    SETTLED = "SETTLED"
