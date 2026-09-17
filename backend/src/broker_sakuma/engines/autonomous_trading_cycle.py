"""AutonomousTradingCycle: the missing Strategy step the PumpFunMonitor's
own docstring calls out (spec sections 3, 22, 28) — once a launch passes
triage as WATCH, something has to propose a concrete, priced order before
the RiskEngine/PaperExecutor can act on it. This is a deliberately simple,
fully-documented strategy (fixed baseline position sizing plus a bounded
learned adjustment, a seeded synthetic exit price) — not a sophisticated
trading algorithm, and not a claim to intelligence it doesn't have, but
genuinely not fixed either: `engines/pattern_learning.py`'s
`PatternLearner` scales each position by how well its liquidity bucket
has actually performed across past round trips (spec section 26).

Every order this proposes still goes through the same `PaperExecutor`
(which itself calls `RiskEngine` and `MaximumLossPolicy`) every other
phase already uses (spec sections 3, 12, 28) — nothing here bypasses a
risk check, and this can never place a real order: `PaperExecutor` only
ever writes to `paper_trades`. It also only ever reacts to
`SyntheticLaunchGenerator`'s clearly-labeled fake launches — this module
is not connected to Pump.fun and cannot be pointed at a real feed without
a real `PumpFunProvider` implementation existing first (spec section 61).

The synthetic exit-price walk is deliberately, and openly, correlated
with a launch's liquidity (higher liquidity skews toward a better
outcome) — a plausible, simple heuristic for a mock feed, not real
market data, and it exists specifically so `PatternLearner` has an
actual, honest pattern to detect instead of pure noise to react to.
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
from broker_sakuma.engines.pattern_learning import PatternLearner
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
        self.learner = PatternLearner(session)

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
        liquidity_usd = decision.liquidity_analysis.liquidity_usd
        entry_price = 1.0

        # Baseline size, then a bounded (0.5x-1.5x) nudge from what this
        # liquidity bucket has actually done in past round trips — still
        # clamped against every existing risk/position limit below, so
        # the learned adjustment can shrink or modestly grow a position,
        # never bypass a cap.
        baseline_usd = bot.capital_operational_usd * self.config.position_fraction_of_capital
        learned_usd = baseline_usd * self.learner.confidence_multiplier(liquidity_usd)
        position_usd = min(learned_usd, self.risk_config.max_position_usd, bot.capital_operational_usd)
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
                liquidity_usd=liquidity_usd,
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

        # A seeded, deterministic-per-launch synthetic price walk, openly
        # biased toward a better outcome the more liquid the launch was —
        # not a market price feed, just a stand-in exit price for the mock
        # launch's whole (instantaneous) lifecycle in this cycle, and the
        # one honest "pattern" PatternLearner is meant to pick up on.
        liquidity_bias = min(0.3, liquidity_usd / 20_000.0)
        price_walk = random.Random(f"{decision.launch.mint_address}:{bot.id}").uniform(
            -0.4 + liquidity_bias, 0.6 + liquidity_bias
        )
        exit_price = max(0.01, entry_price * (1 + price_walk))

        sell = self.executor.execute(
            PaperOrderRequest(
                bot_id=bot.id,
                token_id=decision.token_id,
                side=TradeSide.SELL,
                reference_price=exit_price,
                quantity=quantity,
                liquidity_usd=liquidity_usd,
                slippage_pct=0.01,
            ),
            idempotency_key=f"autocycle-{run_id}-{bot.id}-{decision.token_id}-sell",
        )
        if sell.approved:
            result.trades_executed += 1
            if sell.trade is not None:
                self.learner.record_outcome(bot.id, liquidity_usd, sell.trade.simulated_pnl_usd)
            if sell.bot_died:
                result.bots_died.append(bot.id)
