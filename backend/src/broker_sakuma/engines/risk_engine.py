"""RiskEngine (spec section 28): no order may pass without going through
this engine, and it must see the current global system state.

Kept as a pure function of its inputs (no DB access) so it is trivial to
unit test exhaustively; callers (PaperExecutor, and later the live
executor) are responsible for gathering the day's stats from the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from broker_sakuma.config import RiskPolicyConfig
from broker_sakuma.core.enums import SystemState, TradeSide


@dataclass
class OrderRequest:
    bot_id: str
    side: TradeSide
    price: float
    quantity: float
    liquidity_usd: float
    slippage_pct: float
    wallet_balance_usd: float
    daily_loss_so_far_usd: float
    trades_today_count: int
    consecutive_losses: int

    @property
    def position_usd(self) -> float:
        return self.price * self.quantity


@dataclass
class RiskDecision:
    approved: bool
    violated_rules: list[str] = field(default_factory=list)

    @property
    def reason(self) -> str:
        if self.approved:
            return "approved"
        return "; ".join(self.violated_rules)


class RiskEngine:
    def __init__(self, config: RiskPolicyConfig):
        self.config = config

    def evaluate(self, order: OrderRequest, system_state: SystemState) -> RiskDecision:
        violations: list[str] = []

        if system_state != SystemState.ONLINE:
            violations.append(f"system_state_not_online:{system_state.value}")
            # Nothing else matters once the system isn't ONLINE — fail fast.
            return RiskDecision(approved=False, violated_rules=violations)

        if order.quantity <= 0 or order.price <= 0:
            violations.append("non_positive_price_or_quantity")

        # Like the balance floor above, the position-size cap only gates
        # opening new exposure; exiting an existing position must never be
        # blocked by how large that position has grown.
        if order.side == TradeSide.BUY and order.position_usd > self.config.max_position_usd:
            violations.append(
                f"max_position_usd_exceeded:{order.position_usd:.2f}>{self.config.max_position_usd:.2f}"
            )

        if order.liquidity_usd < self.config.min_liquidity_usd:
            violations.append(
                f"min_liquidity_usd_violated:{order.liquidity_usd:.2f}<{self.config.min_liquidity_usd:.2f}"
            )

        if order.slippage_pct > self.config.max_slippage_pct:
            violations.append(
                f"max_slippage_pct_exceeded:{order.slippage_pct:.4f}>{self.config.max_slippage_pct:.4f}"
            )

        # A SELL reduces exposure and must always be allowed to go through so
        # a bot can never be trapped in a position it cannot exit; the
        # minimum-balance floor only gates opening *new* exposure.
        if order.side == TradeSide.BUY and order.wallet_balance_usd < self.config.min_wallet_balance_usd:
            violations.append(
                f"min_wallet_balance_usd_violated:{order.wallet_balance_usd:.2f}<{self.config.min_wallet_balance_usd:.2f}"
            )

        if order.daily_loss_so_far_usd >= self.config.max_daily_loss_usd:
            violations.append(
                f"max_daily_loss_usd_exceeded:{order.daily_loss_so_far_usd:.2f}>={self.config.max_daily_loss_usd:.2f}"
            )

        if order.trades_today_count >= self.config.max_trades_per_day:
            violations.append(
                f"max_trades_per_day_exceeded:{order.trades_today_count}>={self.config.max_trades_per_day}"
            )

        if order.consecutive_losses >= self.config.max_consecutive_losses:
            violations.append(
                f"max_consecutive_losses_exceeded:{order.consecutive_losses}>={self.config.max_consecutive_losses}"
            )

        return RiskDecision(approved=len(violations) == 0, violated_rules=violations)
