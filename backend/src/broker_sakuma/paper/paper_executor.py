"""PaperExecutor (spec section 4): simulates buy/sell, price, slippage,
fees, P&L, balance and positions exactly as if it were a real operation.

Every order — paper or (eventually) live — must be approved by the
RiskEngine first (spec section 28), and every fill is re-checked against
the MaximumLossPolicy (spec section 12): a bot that crosses its loss
ceiling dies immediately, mid-session, no exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from broker_sakuma.config import RiskPolicyConfig
from broker_sakuma.core.enums import BotState, PositionStatus, TradeSide
from broker_sakuma.db import models
from broker_sakuma.engines.max_loss_policy import MaximumLossPolicy
from broker_sakuma.engines.risk_engine import OrderRequest, RiskDecision, RiskEngine
from broker_sakuma.engines.system_state import get_system_state
from broker_sakuma.engines.telegram_notifications import ProfitNotifier


@dataclass
class PaperOrderRequest:
    bot_id: str
    token_id: str | None
    side: TradeSide
    reference_price: float
    quantity: float
    liquidity_usd: float
    slippage_pct: float
    fee_pct: float = 0.01


@dataclass
class PaperExecutionResult:
    approved: bool
    reason: str
    trade: models.PaperTrade | None = None
    bot_died: bool = False
    duplicate: bool = False


class InsufficientPositionError(Exception):
    """Raised when a SELL is attempted for more than the bot currently holds."""


class PaperExecutor:
    def __init__(self, session: Session, risk_config: RiskPolicyConfig, notifier: ProfitNotifier | None = None):
        self.session = session
        self.risk_engine = RiskEngine(risk_config)
        self.max_loss_policy = MaximumLossPolicy()
        self.notifier = notifier

    def _today_stats(self, bot_id: str) -> tuple[float, int, int]:
        """Return (loss_so_far_usd, trades_count, consecutive_losses) for today."""

        stmt = (
            select(models.PaperTrade)
            .where(models.PaperTrade.bot_id == bot_id)
            .order_by(models.PaperTrade.executed_at.asc())
        )
        all_trades = list(self.session.execute(stmt).scalars())
        today = datetime.now(timezone.utc).date()
        todays = [t for t in all_trades if t.executed_at.date() == today]

        loss_so_far = -sum(t.simulated_pnl_usd for t in todays if t.simulated_pnl_usd < 0)
        trades_count = len(todays)

        consecutive_losses = 0
        for t in reversed(all_trades):
            if t.simulated_pnl_usd < 0:
                consecutive_losses += 1
            elif t.simulated_pnl_usd > 0:
                break
        return loss_so_far, trades_count, consecutive_losses

    def _open_position(self, bot_id: str, token_id: str) -> models.Position | None:
        stmt = select(models.Position).where(
            models.Position.bot_id == bot_id,
            models.Position.token_id == token_id,
            models.Position.status == PositionStatus.OPEN,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def execute(self, order: PaperOrderRequest, idempotency_key: str) -> PaperExecutionResult:
        existing = self.session.execute(
            select(models.PaperTrade).where(models.PaperTrade.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if existing is not None:
            return PaperExecutionResult(approved=True, reason="duplicate_idempotency_key", trade=existing, duplicate=True)

        bot = self.session.get(models.Bot, order.bot_id)
        if bot is None:
            return PaperExecutionResult(approved=False, reason="bot_not_found")
        if bot.state == BotState.DEAD:
            return PaperExecutionResult(approved=False, reason="bot_is_dead")

        system_state = get_system_state(self.session)
        loss_so_far, trades_count, consecutive_losses = self._today_stats(bot.id)

        risk_order = OrderRequest(
            bot_id=bot.id,
            side=order.side,
            price=order.reference_price,
            quantity=order.quantity,
            liquidity_usd=order.liquidity_usd,
            slippage_pct=order.slippage_pct,
            wallet_balance_usd=bot.capital_operational_usd,
            daily_loss_so_far_usd=loss_so_far,
            trades_today_count=trades_count,
            consecutive_losses=consecutive_losses,
        )
        decision: RiskDecision = self.risk_engine.evaluate(risk_order, system_state)
        if not decision.approved:
            self.session.add(
                models.RiskEvent(
                    bot_id=bot.id,
                    event_type="ORDER_REJECTED",
                    severity="WARNING",
                    details={"reason": decision.reason},
                )
            )
            self.session.commit()
            return PaperExecutionResult(approved=False, reason=decision.reason)

        if order.side == TradeSide.BUY:
            executed_price = order.reference_price * (1 + order.slippage_pct)
        else:
            executed_price = order.reference_price * (1 - order.slippage_pct)

        gross_usd = executed_price * order.quantity
        fee_usd = gross_usd * order.fee_pct
        realized_pnl_usd = 0.0

        position = self._open_position(bot.id, order.token_id) if order.token_id else None

        if order.side == TradeSide.BUY:
            cost_usd = gross_usd + fee_usd
            bot.capital_operational_usd -= cost_usd
            if order.token_id:
                if position is None:
                    position = models.Position(
                        bot_id=bot.id,
                        token_id=order.token_id,
                        quantity=order.quantity,
                        avg_entry_price=executed_price,
                        status=PositionStatus.OPEN,
                    )
                    self.session.add(position)
                else:
                    total_qty = position.quantity + order.quantity
                    position.avg_entry_price = (
                        position.avg_entry_price * position.quantity + executed_price * order.quantity
                    ) / total_qty
                    position.quantity = total_qty
        else:
            if position is None or position.quantity < order.quantity:
                raise InsufficientPositionError(
                    f"bot {bot.id} cannot sell {order.quantity} of token {order.token_id}: "
                    f"open position is {position.quantity if position else 0}"
                )
            proceeds_usd = gross_usd - fee_usd
            realized_pnl_usd = (executed_price - position.avg_entry_price) * order.quantity - fee_usd
            bot.capital_operational_usd += proceeds_usd
            bot.cumulative_pnl_usd += realized_pnl_usd
            position.quantity -= order.quantity
            if position.quantity <= 1e-12:
                position.status = PositionStatus.CLOSED
                position.closed_at = datetime.now(timezone.utc)

        current_equity = bot.capital_operational_usd + bot.reserve_usd
        bot.peak_equity_usd = max(bot.peak_equity_usd, current_equity)
        bot.drawdown_pct = (
            max(0.0, (bot.peak_equity_usd - current_equity) / bot.peak_equity_usd)
            if bot.peak_equity_usd > 0
            else 0.0
        )

        bot.trades_count += 1

        trade = models.PaperTrade(
            bot_id=bot.id,
            token_id=order.token_id,
            side=order.side,
            price=executed_price,
            quantity=order.quantity,
            fee_usd=fee_usd,
            slippage_pct=order.slippage_pct,
            simulated_pnl_usd=realized_pnl_usd,
            idempotency_key=idempotency_key,
            executed_at=datetime.now(timezone.utc),
        )
        self.session.add(trade)
        self.session.add(bot)

        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.session.execute(
                select(models.PaperTrade).where(models.PaperTrade.idempotency_key == idempotency_key)
            ).scalar_one_or_none()
            return PaperExecutionResult(approved=True, reason="duplicate_idempotency_key", trade=existing, duplicate=True)

        bot_died = self.max_loss_policy.enforce(self.session, bot, reason="max_loss_breached_during_paper_trading")

        if self.notifier is not None:
            self.notifier.notify_profit(bot, trade)

        return PaperExecutionResult(approved=True, reason="executed", trade=trade, bot_died=bot_died)
