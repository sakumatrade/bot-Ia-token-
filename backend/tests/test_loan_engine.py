from __future__ import annotations

import pytest

from broker_sakuma.config import LoanPolicyConfig
from broker_sakuma.core.enums import BotState, InterestModel, LoanStatus
from broker_sakuma.db import models
from broker_sakuma.engines.loan_engine import BotLoanEngine, LoanExposureExceeded


@pytest.fixture()
def mother_and_son(db_session):
    mother = models.Bot(name="Mother Bot", generation=0, capital_operational_usd=1000.0, state=BotState.ACTIVE)
    son = models.Bot(name="Son 070", parent_id=None, generation=1, state=BotState.ACTIVE)
    db_session.add_all([mother, son])
    db_session.commit()
    son.parent_id = mother.id
    db_session.add(son)
    db_session.commit()
    return mother, son


def test_mother_exposure_limit_is_enforced(db_session, mother_and_son):
    """Spec section 57: Mother has $1,000, limit 20% -> max exposure $200."""

    mother, son = mother_and_son
    engine = BotLoanEngine(db_session, LoanPolicyConfig(mother_max_total_loan_pct_of_treasury=0.20))

    engine.create_loan(mother, son, principal_usd=150.0, purpose="thesis funding")

    with pytest.raises(LoanExposureExceeded):
        engine.create_loan(mother, son, principal_usd=100.0, purpose="more funding")  # 150+100=250 > 200


def test_loan_updates_balances_and_records_funding_event(db_session, mother_and_son):
    mother, son = mother_and_son
    engine = BotLoanEngine(db_session, LoanPolicyConfig(mother_max_total_loan_pct_of_treasury=0.20))

    loan = engine.create_loan(mother, son, principal_usd=100.0, purpose="thesis funding")

    assert loan.status == LoanStatus.ACTIVE
    assert loan.remaining_balance_usd == 100.0
    assert mother.capital_operational_usd == 900.0
    assert son.capital_operational_usd == 100.0
    assert son.capital_borrowed_usd == 100.0

    funding = db_session.query(models.FundingEvent).filter_by(bot_id=son.id, funding_type="loan").one()
    assert funding.amount_usd == 100.0


def test_cannot_lend_to_dead_bot(db_session, mother_and_son):
    mother, son = mother_and_son
    son.state = BotState.DEAD
    db_session.add(son)
    db_session.commit()

    engine = BotLoanEngine(db_session, LoanPolicyConfig())
    with pytest.raises(ValueError):
        engine.create_loan(mother, son, principal_usd=10.0)


def test_loan_repayment_with_profit_share_interest(db_session, mother_and_son):
    """Spec section 56: Mother lends $100, bot makes $20 profit."""

    mother, son = mother_and_son
    loan_config = LoanPolicyConfig(mother_max_total_loan_pct_of_treasury=0.50, profit_share_rate=0.10)
    loan_engine = BotLoanEngine(db_session, loan_config)

    loan = loan_engine.create_loan(
        mother, son, principal_usd=100.0, interest_model=InterestModel.PROFIT_SHARE, purpose="thesis"
    )

    from broker_sakuma.engines.loan_interest_engine import BotLoanInterestEngine

    interest_engine = BotLoanInterestEngine(loan_config)
    interest_usd = interest_engine.compute_interest(loan, profit_usd=20.0)
    assert interest_usd == pytest.approx(2.0)  # 20 * 10%

    payment = loan_engine.record_payment(loan, principal_component_usd=100.0, interest_component_usd=interest_usd)
    assert payment.amount_usd == pytest.approx(102.0)
    assert loan.status == LoanStatus.PAID
    assert loan.remaining_balance_usd == 0.0


def test_no_profit_means_no_invented_profit_share_interest(db_session, mother_and_son):
    mother, son = mother_and_son
    loan_config = LoanPolicyConfig(mother_max_total_loan_pct_of_treasury=0.50, profit_share_rate=0.10)
    loan_engine = BotLoanEngine(db_session, loan_config)
    loan = loan_engine.create_loan(mother, son, principal_usd=100.0, interest_model=InterestModel.PROFIT_SHARE)

    from broker_sakuma.engines.loan_interest_engine import BotLoanInterestEngine

    interest_engine = BotLoanInterestEngine(loan_config)
    assert interest_engine.compute_interest(loan, profit_usd=0.0) == 0.0
    assert interest_engine.compute_interest(loan, profit_usd=-50.0) == 0.0


def test_fixed_interest_applies_regardless_of_profit(db_session, mother_and_son):
    mother, son = mother_and_son
    loan_config = LoanPolicyConfig(mother_max_total_loan_pct_of_treasury=0.50, fixed_interest_rate=0.05)
    loan_engine = BotLoanEngine(db_session, loan_config)
    loan = loan_engine.create_loan(mother, son, principal_usd=100.0, interest_model=InterestModel.FIXED)

    from broker_sakuma.engines.loan_interest_engine import BotLoanInterestEngine

    interest_engine = BotLoanInterestEngine(loan_config)
    assert interest_engine.compute_interest(loan, profit_usd=0.0) == pytest.approx(5.0)


def test_hybrid_interest_combines_both_components(db_session, mother_and_son):
    mother, son = mother_and_son
    loan_config = LoanPolicyConfig(
        mother_max_total_loan_pct_of_treasury=0.50,
        hybrid_fixed_component=0.01,
        hybrid_profit_share_component=0.05,
    )
    loan_engine = BotLoanEngine(db_session, loan_config)
    loan = loan_engine.create_loan(mother, son, principal_usd=100.0, interest_model=InterestModel.HYBRID)

    from broker_sakuma.engines.loan_interest_engine import BotLoanInterestEngine

    interest_engine = BotLoanInterestEngine(loan_config)
    interest_usd = interest_engine.compute_interest(loan, profit_usd=20.0)
    assert interest_usd == pytest.approx(100 * 0.01 + 20 * 0.05)  # 1.0 + 1.0
