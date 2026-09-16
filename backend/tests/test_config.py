from __future__ import annotations

from broker_sakuma.config import Environment, Settings


def test_defaults_are_safe():
    settings = Settings()
    assert settings.environment == Environment.SIMULATION
    assert settings.trading.live_trading_enabled is False


def test_thesis_default_is_five_dollars():
    settings = Settings()
    assert settings.thesis.initial_test_capital_usd == 5.0


def test_loan_exposure_limit_is_explicit_and_overridable():
    settings = Settings(loan={"mother_max_total_loan_pct_of_treasury": 0.35})
    assert settings.loan.mother_max_total_loan_pct_of_treasury == 0.35


def test_settlement_percentages_sum_to_one_by_default():
    settings = Settings()
    total = (
        settings.settlement.operational_capital_retention_pct
        + settings.settlement.reserve_contribution_pct
        + settings.settlement.returned_to_mother_pct
    )
    assert abs(total - 1.0) < 1e-9
