"""BotLoanInterestEngine (spec section 18): configurable interest models.

If a bot had no profit, we never invent one — PROFIT_SHARE and the
profit-linked half of HYBRID both floor at zero. FIXED is the one model
that charges interest regardless of profit, and only because choosing it
is itself an explicit policy decision (spec: "aplicar somente juros fixos
se essa política estiver explicitamente configurada").
"""

from __future__ import annotations

from broker_sakuma.config import LoanPolicyConfig
from broker_sakuma.core.enums import InterestModel
from broker_sakuma.db import models


class BotLoanInterestEngine:
    def __init__(self, config: LoanPolicyConfig):
        self.config = config

    def compute_interest(self, loan: models.BotLoan, profit_usd: float) -> float:
        model = InterestModel(loan.interest_model)

        if model == InterestModel.FIXED:
            return loan.principal_usd * loan.interest_rate

        if model == InterestModel.PROFIT_SHARE:
            return max(profit_usd, 0.0) * loan.interest_rate

        if model == InterestModel.HYBRID:
            fixed_part = loan.principal_usd * self.config.hybrid_fixed_component
            profit_part = max(profit_usd, 0.0) * self.config.hybrid_profit_share_component
            return fixed_part + profit_part

        raise ValueError(f"unknown interest model: {loan.interest_model}")
