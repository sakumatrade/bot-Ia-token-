from __future__ import annotations

from datetime import date

import pytest

from broker_sakuma.core.enums import DatasetSplit, StrategyState
from broker_sakuma.db import models
from broker_sakuma.engines.backtest_engine import (
    BacktestDataset,
    BacktestEngine,
    BacktestRuleViolation,
    LookAheadBiasError,
)


@pytest.fixture()
def strategy(db_session):
    s = models.Strategy(name="Pump.fun creator momentum")
    db_session.add(s)
    db_session.commit()
    return s


def flat_return_strategy_fn(series: list[tuple[date, float]]) -> dict:
    if len(series) < 2:
        return {"return_pct": 0.0, "trades": 0}
    start_price = series[0][1]
    end_price = series[-1][1]
    return {"return_pct": (end_price - start_price) / start_price, "trades": len(series) - 1}


def test_create_strategy_version_starts_in_research(db_session, strategy):
    engine = BacktestEngine(db_session)
    sv = engine.create_strategy_version(strategy, version="1", params={"lookback_days": 3})
    assert sv.state == StrategyState.RESEARCH


def test_split_ordering_rejects_overlap():
    train = BacktestDataset(DatasetSplit.TRAIN, date(2026, 1, 1), date(2026, 2, 1), [])
    validation = BacktestDataset(DatasetSplit.VALIDATION, date(2026, 1, 15), date(2026, 2, 15), [])  # overlaps train
    test = BacktestDataset(DatasetSplit.TEST, date(2026, 3, 1), date(2026, 3, 15), [])

    with pytest.raises(LookAheadBiasError):
        BacktestEngine.validate_split_ordering(train, validation, test)


def test_split_ordering_accepts_strictly_increasing_windows():
    train = BacktestDataset(DatasetSplit.TRAIN, date(2026, 1, 1), date(2026, 1, 31), [])
    validation = BacktestDataset(DatasetSplit.VALIDATION, date(2026, 2, 1), date(2026, 2, 15), [])
    test = BacktestDataset(DatasetSplit.TEST, date(2026, 3, 1), date(2026, 3, 15), [])

    BacktestEngine.validate_split_ordering(train, validation, test)  # must not raise


def test_run_backtest_trims_data_outside_the_split_window(db_session, strategy):
    engine = BacktestEngine(db_session)
    sv = engine.create_strategy_version(strategy, version="1", params={})

    series = [
        (date(2025, 12, 31), 1.0),  # before window — must be trimmed
        (date(2026, 1, 1), 1.0),
        (date(2026, 1, 15), 1.5),
        (date(2026, 1, 31), 2.0),
        (date(2026, 2, 5), 999.0),  # after window (future data) — must be trimmed
    ]
    dataset = BacktestDataset(DatasetSplit.TRAIN, date(2026, 1, 1), date(2026, 1, 31), series)

    received = {}

    def spy_strategy_fn(windowed_series):
        received["series"] = windowed_series
        return flat_return_strategy_fn(windowed_series)

    backtest = engine.run_backtest(sv, dataset, spy_strategy_fn)

    assert received["series"] == series[1:4]  # only the three in-window points
    assert backtest.metrics["return_pct"] == pytest.approx(1.0)  # 1.0 -> 2.0
    assert sv.state == StrategyState.BACKTEST  # auto-advanced from RESEARCH


def test_cannot_promote_to_paper_without_test_split_backtest(db_session, strategy):
    engine = BacktestEngine(db_session)
    sv = engine.create_strategy_version(strategy, version="1", params={})

    train_data = BacktestDataset(DatasetSplit.TRAIN, date(2026, 1, 1), date(2026, 1, 31), [(date(2026, 1, 1), 1.0)])
    engine.run_backtest(sv, train_data, flat_return_strategy_fn)

    with pytest.raises(BacktestRuleViolation):
        engine.promote_to_paper(sv)


def test_full_lifecycle_train_validation_test_paper_review_approved(db_session, strategy):
    engine = BacktestEngine(db_session)
    sv = engine.create_strategy_version(strategy, version="1", params={})

    train = BacktestDataset(DatasetSplit.TRAIN, date(2026, 1, 1), date(2026, 1, 31), [(date(2026, 1, 15), 1.0)])
    validation = BacktestDataset(DatasetSplit.VALIDATION, date(2026, 2, 1), date(2026, 2, 15), [(date(2026, 2, 5), 1.0)])
    test = BacktestDataset(DatasetSplit.TEST, date(2026, 3, 1), date(2026, 3, 15), [(date(2026, 3, 5), 1.0)])

    BacktestEngine.validate_split_ordering(train, validation, test)

    engine.run_backtest(sv, train, flat_return_strategy_fn)
    assert sv.state == StrategyState.BACKTEST

    engine.run_backtest(sv, validation, flat_return_strategy_fn)
    engine.run_backtest(sv, test, flat_return_strategy_fn)

    engine.promote_to_paper(sv)
    assert sv.state == StrategyState.PAPER

    engine.send_to_review(sv)
    assert sv.state == StrategyState.REVIEW

    engine.approve(sv)
    assert sv.state == StrategyState.APPROVED


def test_cannot_run_backtest_on_approved_strategy(db_session, strategy):
    engine = BacktestEngine(db_session)
    sv = engine.create_strategy_version(strategy, version="1", params={})
    test = BacktestDataset(DatasetSplit.TEST, date(2026, 3, 1), date(2026, 3, 15), [(date(2026, 3, 5), 1.0)])
    engine.run_backtest(sv, test, flat_return_strategy_fn)
    engine.promote_to_paper(sv)
    engine.send_to_review(sv)
    engine.approve(sv)

    with pytest.raises(BacktestRuleViolation):
        engine.run_backtest(sv, test, flat_return_strategy_fn)
