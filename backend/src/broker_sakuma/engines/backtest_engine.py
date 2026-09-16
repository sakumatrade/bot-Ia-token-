"""BacktestEngine (spec section 27): TRAIN / VALIDATION / TEST are kept
strictly separate and strictly ordered in time, strategies are versioned,
and no split ever sees a data point outside its own date window — the
concrete defenses this engine provides against look-ahead bias and data
leakage. Overfitting isn't something code can rule out by itself; the best
this layer can do is make sure promotion to PAPER requires real evidence
(an actual TEST-split backtest on record) rather than a research vibe.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from broker_sakuma.core.enums import DatasetSplit, StrategyState
from broker_sakuma.db import models

_ALLOWED_TRANSITIONS: dict[StrategyState, set[StrategyState]] = {
    StrategyState.RESEARCH: {StrategyState.BACKTEST, StrategyState.DISABLED},
    StrategyState.BACKTEST: {StrategyState.PAPER, StrategyState.DISABLED},
    StrategyState.PAPER: {StrategyState.REVIEW, StrategyState.DISABLED},
    StrategyState.REVIEW: {StrategyState.APPROVED, StrategyState.BACKTEST, StrategyState.DISABLED},
    StrategyState.APPROVED: {StrategyState.DISABLED},
    StrategyState.DISABLED: set(),
}


class BacktestRuleViolation(Exception):
    pass


class LookAheadBiasError(BacktestRuleViolation):
    """Raised when TRAIN/VALIDATION/TEST windows overlap or run out of order."""


@dataclass
class BacktestDataset:
    split: DatasetSplit
    start_date: date
    end_date: date
    price_series: list[tuple[date, float]]


class BacktestEngine:
    def __init__(self, session: Session):
        self.session = session

    def create_strategy_version(self, strategy: models.Strategy, version: str, params: dict) -> models.StrategyVersion:
        sv = models.StrategyVersion(
            strategy_id=strategy.id, version=version, params=params, state=StrategyState.RESEARCH
        )
        self.session.add(sv)
        self.session.commit()
        return sv

    def _transition(self, strategy_version: models.StrategyVersion, to_state: StrategyState) -> None:
        current = StrategyState(strategy_version.state)
        if to_state not in _ALLOWED_TRANSITIONS[current]:
            raise BacktestRuleViolation(f"cannot move strategy version from {current.value} to {to_state.value}")
        strategy_version.state = to_state

    @staticmethod
    def validate_split_ordering(train: BacktestDataset, validation: BacktestDataset, test: BacktestDataset) -> None:
        """TRAIN must fully precede VALIDATION, which must fully precede
        TEST. This is the structural guard against look-ahead bias across
        splits — it is checked before any strategy function ever runs.
        """

        if train.split != DatasetSplit.TRAIN or validation.split != DatasetSplit.VALIDATION or test.split != DatasetSplit.TEST:
            raise BacktestRuleViolation("datasets were not passed in TRAIN/VALIDATION/TEST order")
        if not (train.end_date < validation.start_date):
            raise LookAheadBiasError(
                f"TRAIN (ends {train.end_date}) overlaps or leaks into VALIDATION (starts {validation.start_date})"
            )
        if not (validation.end_date < test.start_date):
            raise LookAheadBiasError(
                f"VALIDATION (ends {validation.end_date}) overlaps or leaks into TEST (starts {test.start_date})"
            )

    def run_backtest(
        self,
        strategy_version: models.StrategyVersion,
        dataset: BacktestDataset,
        strategy_fn: Callable[[list[tuple[date, float]]], dict],
    ) -> models.Backtest:
        """Run ``strategy_fn`` against exactly the data inside
        ``dataset``'s own window — points outside it are trimmed before the
        function ever sees them, so a caller cannot accidentally leak
        future data into a TRAIN or VALIDATION run.
        """

        if StrategyState(strategy_version.state) not in (StrategyState.RESEARCH, StrategyState.BACKTEST):
            raise BacktestRuleViolation(
                f"strategy version {strategy_version.id} is {strategy_version.state}; must be RESEARCH or BACKTEST to run a backtest"
            )

        windowed_series = [
            (d, p) for d, p in dataset.price_series if dataset.start_date <= d <= dataset.end_date
        ]
        metrics = strategy_fn(windowed_series)

        backtest = models.Backtest(
            strategy_version_id=strategy_version.id,
            dataset_split=dataset.split.value,
            start_date=dataset.start_date,
            end_date=dataset.end_date,
            metrics=metrics,
        )
        self.session.add(backtest)

        if StrategyState(strategy_version.state) == StrategyState.RESEARCH:
            self._transition(strategy_version, StrategyState.BACKTEST)
            self.session.add(strategy_version)

        self.session.commit()
        return backtest

    def promote_to_paper(self, strategy_version: models.StrategyVersion) -> models.StrategyVersion:
        """Only promotable once at least one TEST-split backtest is on
        record — evidence, not vibes."""

        has_test_backtest = self.session.execute(
            select(models.Backtest).where(
                models.Backtest.strategy_version_id == strategy_version.id,
                models.Backtest.dataset_split == DatasetSplit.TEST.value,
            )
        ).first()
        if has_test_backtest is None:
            raise BacktestRuleViolation(
                f"strategy version {strategy_version.id} has no TEST-split backtest on record; cannot promote to PAPER"
            )

        self._transition(strategy_version, StrategyState.PAPER)
        self.session.add(strategy_version)
        self.session.commit()
        return strategy_version

    def send_to_review(self, strategy_version: models.StrategyVersion) -> models.StrategyVersion:
        self._transition(strategy_version, StrategyState.REVIEW)
        self.session.add(strategy_version)
        self.session.commit()
        return strategy_version

    def approve(self, strategy_version: models.StrategyVersion) -> models.StrategyVersion:
        self._transition(strategy_version, StrategyState.APPROVED)
        self.session.add(strategy_version)
        self.session.commit()
        return strategy_version

    def disable(self, strategy_version: models.StrategyVersion, reason: str) -> models.StrategyVersion:
        strategy_version.state = StrategyState.DISABLED
        self.session.add(strategy_version)
        self.session.add(
            models.AuditLog(
                actor="backtest_engine",
                action="STRATEGY_VERSION_DISABLED",
                entity_type="strategy_version",
                entity_id=strategy_version.id,
                details={"reason": reason},
            )
        )
        self.session.commit()
        return strategy_version
