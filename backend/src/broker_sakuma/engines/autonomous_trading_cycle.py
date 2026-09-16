"""AutonomousTradingCycle: the missing Strategy step the PumpFunMonitor's
own docstring calls out (spec sections 3, 22, 28) — once a launch passes
triage as WATCH, something has to propose a concrete, priced order before
the RiskEngine/PaperExecutor can act on it. This is a deliberately simple,
fully-documented placeholder strategy (fixed position sizing, a seeded
synthetic exit price), not a sophisticated trading algorithm — it exists
so an activated bot can trade *on its own*, with no manual
`/api/system/run-cycle` call needed per trade, not to claim intelligence
it doesn't have.

Every order this proposes still goes through the same `PaperExecutor`
(which itself calls `RiskEngine` and `MaximumLossPolicy`) every other
phase already uses (spec sections 3, 12, 28) — nothing here bypasses a
risk check, and this can never place a real order: `PaperExecutor` only
ever writes to `paper_trades`. It also only ever reacts to
`SyntheticLaunchGenerator`'s clearly-labeled fake launches — this module
is not connected to Pump.fun and cannot be pointed at a real feed without
a real `PumpFunProvider` implementation existing first (spec section 61).
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from broker_sakuma.adapters.pumpfun.monitor import PumpFunMonitor
from broker_sakuma.adapters.pumpfun.provider import PumpFunProvider
from broker_sakuma.config import AutoTradingConfig, RiskPolicyConfig
from broker_sakuma.core.enums import BotState, ThesisState, TradeSide
from broker_sakuma.db import models
from broker_sakuma.engines.telegram_notifications import ProfitNotifier
from broker_sakuma.paper.paper_executor import PaperExecutor, PaperOrderRequest


@dataclass
class CycleResult:
    decisions_evaluated: int = 0
    trades_executed: int = 0
    bots_died: list[str] = field(default_factory=list)


class AutonomousTradingCycle:
    def __init__(
        self,
        session: Session,
        provider: PumpFunProvider,
        risk_config: RiskPolicyConfig,
        auto_trading_config: AutoTradingConfig,
        notifier: ProfitNotifier | None = None,
    ):
        self.session = session
        self.risk_config = risk_config
        self.config = auto_trading_config
        self.monitor = PumpFunMonitor(session, provider, risk_config)
        self.executor = PaperExecutor(session, risk_config, notifier=notifier)

    def _tradeable_bots(self) -> list[models.Bot]:
        """Active bots with a thesis that has actually started (spec
        section 10's $5 rule already funded it) — a bot with no thesis
        yet, or one still in RESEARCH/BACKTEST/PAPER, is not tradeable."""

        bots = list(self.session.execute(select(models.Bot).where(models.Bot.state == BotState.ACTIVE)).scalars())
        tradeable_states = {ThesisState.INITIAL_TEST, ThesisState.VALIDATION, ThesisState.APPROVED}
        tradeable: list[models.Bot] = []
        for bot in bots:
            has_thesis = self.session.execute(
                select(models.Thesis.id).where(models.Thesis.bot_id == bot.id, models.Thesis.state.in_(tradeable_states))
            ).first()
            if has_thesis is not None:
                tradeable.append(bot)
        return tradeable

    def run_once(self) -> CycleResult:
        decisions = self.monitor.poll()
        bots = self._tradeable_bots()
        result = CycleResult(decisions_evaluated=len(decisions))
        run_id = uuid.uuid4().hex

        for decision in decisions:
            if decision.action != "WATCH":
                continue
            for bot in bots:
                if bot.id in result.bots_died or bot.state == BotState.DEAD:
                    continue
                self._trade_one(bot, decision, run_id, result)

        return result

    def _trade_one(self, bot: models.Bot, decision, run_id: str, result: CycleResult) -> None:
        entry_price = 1.0
        position_usd = min(
            bot.capital_operational_usd * self.config.position_fraction_of_capital,
            self.risk_config.max_position_usd,
            bot.capital_operational_usd,
        )
        if position_usd < 0.01:
            return
        quantity = position_usd / entry_price

        buy = self.executor.execute(
            PaperOrderRequest(
                bot_id=bot.id,
                token_id=decision.token_id,
                side=TradeSide.BUY,
                reference_price=entry_price,
                quantity=quantity,
                liquidity_usd=decision.liquidity_analysis.liquidity_usd,
                slippage_pct=0.01,
            ),
            idempotency_key=f"autocycle-{run_id}-{bot.id}-{decision.token_id}-buy",
        )
        if not buy.approved:
            return
        result.trades_executed += 1
        if buy.bot_died:
            result.bots_died.append(bot.id)
            return

        # A seeded, deterministic-per-launch synthetic price walk — this is
        # not a market price feed, just a stand-in exit price for the mock
        # launch's whole (instantaneous) lifecycle in this cycle.
        price_walk = random.Random(f"{decision.launch.mint_address}:{bot.id}").uniform(-0.4, 0.6)
        exit_price = max(0.01, entry_price * (1 + price_walk))

        sell = self.executor.execute(
            PaperOrderRequest(
                bot_id=bot.id,
                token_id=decision.token_id,
                side=TradeSide.SELL,
                reference_price=exit_price,
                quantity=quantity,
                liquidity_usd=decision.liquidity_analysis.liquidity_usd,
                slippage_pct=0.01,
            ),
            idempotency_key=f"autocycle-{run_id}-{bot.id}-{decision.token_id}-sell",
        )
        if sell.approved:
            result.trades_executed += 1
            if sell.bot_died:
                result.bots_died.append(bot.id)
