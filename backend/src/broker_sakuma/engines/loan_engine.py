"""BotLoanEngine (spec section 17): Mother Bot acts as an internal
treasury. It may never lend out its whole patrimony — the exposure limit
is an explicit, configured percentage, never a hardcoded number.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from broker_sakuma.config import LoanPolicyConfig
from broker_sakuma.core.enums import BotState, InterestModel, LoanStatus
from broker_sakuma.db import models


class LoanExposureExceeded(Exception):
    """Raised when a loan would push Mother's total outstanding exposure
    past ``LoanPolicyConfig.mother_max_total_loan_pct_of_treasury``."""


class BotLoanEngine:
    def __init__(self, session: Session, config: LoanPolicyConfig):
        self.session = session
        self.config = config

    def _total_active_loan_principal(self, mother_id: str) -> float:
        stmt = select(func.sum(models.BotLoan.remaining_balance_usd)).where(
            models.BotLoan.mother_id == mother_id,
            models.BotLoan.status == LoanStatus.ACTIVE,
        )
        total = self.session.execute(stmt).scalar()
        return total or 0.0

    def _default_rate_for(self, model: InterestModel) -> float:
        if model == InterestModel.FIXED:
            return self.config.fixed_interest_rate
        if model == InterestModel.PROFIT_SHARE:
            return self.config.profit_share_rate
        return 0.0  # HYBRID pulls its two components straight from config in the interest engine

    def create_loan(
        self,
        mother: models.Bot,
        bot: models.Bot,
        principal_usd: float,
        purpose: str | None = None,
        thesis_id: str | None = None,
        term_days: int | None = None,
        interest_model: InterestModel | None = None,
        interest_rate: float | None = None,
    ) -> models.BotLoan:
        if bot.state == BotState.DEAD:
            raise ValueError(f"cannot lend to bot {bot.id}: it is DEAD")
        if principal_usd <= 0:
            raise ValueError("principal_usd must be positive")

        max_exposure = mother.capital_operational_usd * self.config.mother_max_total_loan_pct_of_treasury
        current_exposure = self._total_active_loan_principal(mother.id)
        if current_exposure + principal_usd > max_exposure + 1e-9:
            raise LoanExposureExceeded(
                f"loan of {principal_usd:.2f} would push Mother exposure to "
                f"{current_exposure + principal_usd:.2f}, exceeding the limit of {max_exposure:.2f} "
                f"({self.config.mother_max_total_loan_pct_of_treasury:.0%} of {mother.capital_operational_usd:.2f})"
            )

        model = interest_model or self.config.default_interest_model
        rate = interest_rate if interest_rate is not None else self._default_rate_for(model)

        loan = models.BotLoan(
            loan_id=f"loan-{uuid.uuid4()}",
            bot_id=bot.id,
            mother_id=mother.id,
            principal_usd=principal_usd,
            purpose=purpose,
            thesis_id=thesis_id,
            term_days=term_days,
            interest_model=model,
            interest_rate=rate,
            status=LoanStatus.ACTIVE,
            remaining_balance_usd=principal_usd,
        )
        self.session.add(loan)

        mother.capital_operational_usd -= principal_usd
        bot.capital_operational_usd += principal_usd
        bot.capital_borrowed_usd += principal_usd
        self.session.add(mother)
        self.session.add(bot)

        self.session.add(
            models.FundingEvent(
                bot_id=bot.id,
                mother_id=mother.id,
                amount_usd=principal_usd,
                funding_type="loan",
                reason=purpose,
            )
        )
        self.session.commit()

        self.session.add(
            models.AuditLog(
                actor="bot_loan_engine",
                action="LOAN_CREATED",
                entity_type="bot_loan",
                entity_id=loan.id,
                details={"principal_usd": principal_usd, "bot_id": bot.id, "mother_id": mother.id},
            )
        )
        self.session.commit()
        return loan

    def record_payment(
        self,
        loan: models.BotLoan,
        principal_component_usd: float,
        interest_component_usd: float,
    ) -> models.LoanPayment:
        if loan.status != LoanStatus.ACTIVE:
            raise ValueError(f"cannot pay loan {loan.id}: status is {loan.status}, not ACTIVE")
        if principal_component_usd < 0 or interest_component_usd < 0:
            raise ValueError("payment components cannot be negative")

        loan.remaining_balance_usd = max(0.0, loan.remaining_balance_usd - principal_component_usd)
        if loan.remaining_balance_usd <= 1e-9:
            loan.status = LoanStatus.PAID
        self.session.add(loan)

        payment = models.LoanPayment(
            loan_id=loan.id,
            amount_usd=principal_component_usd + interest_component_usd,
            principal_component_usd=principal_component_usd,
            interest_component_usd=interest_component_usd,
            remaining_balance_usd=loan.remaining_balance_usd,
        )
        self.session.add(payment)

        mother = self.session.get(models.Bot, loan.mother_id)
        if mother is not None:
            mother.capital_operational_usd += principal_component_usd + interest_component_usd
            self.session.add(mother)

        self.session.commit()
        return payment
