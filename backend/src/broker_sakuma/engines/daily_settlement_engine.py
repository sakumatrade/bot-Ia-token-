"""DailySettlementEngine (spec section 19): at the end of each day, compute
result, fees, interest, loan repayment, capital to return to Mother, capital
retained for operations, and the reserve contribution — all as explicit,
configured percentages, never hidden in code.

A losing day is never redistributed to reserve or Mother: the whole net
loss is simply carried as reduced operational capital.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from broker_sakuma.config import SettlementPolicyConfig
from broker_sakuma.db import models
from broker_sakuma.engines.reserve_growth_engine import ReserveGrowthEngine


class AlreadySettledError(Exception):
    """Raised when attempting to settle a bot for a date already settled."""


class DailySettlementEngine:
    def __init__(self, session: Session, config: SettlementPolicyConfig, reserve_engine: ReserveGrowthEngine):
        self.session = session
        self.config = config
        self.reserve_engine = reserve_engine

    def settle(
        self,
        bot: models.Bot,
        settlement_date: date,
        gross_result_usd: float,
        fees_usd: float = 0.0,
        interest_usd: float = 0.0,
        loan_repayment_usd: float = 0.0,
    ) -> models.DailySettlement:
        existing = self.session.execute(
            select(models.DailySettlement).where(
                models.DailySettlement.bot_id == bot.id,
                models.DailySettlement.settlement_date == settlement_date,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise AlreadySettledError(f"bot {bot.id} already has a settlement for {settlement_date}")

        net_result_usd = gross_result_usd - fees_usd - interest_usd - loan_repayment_usd

        if net_result_usd > 0:
            retained = net_result_usd * self.config.operational_capital_retention_pct
            reserve_contribution = net_result_usd * self.config.reserve_contribution_pct
            returned_to_mother = net_result_usd * self.config.returned_to_mother_pct
        else:
            retained = net_result_usd
            reserve_contribution = 0.0
            returned_to_mother = 0.0

        bot.capital_borrowed_usd = max(0.0, bot.capital_borrowed_usd - loan_repayment_usd)
        bot.capital_operational_usd += retained
        self.session.add(bot)

        if reserve_contribution > 0:
            self.reserve_engine.contribute(
                bot.id, reserve_contribution, reason=f"daily settlement {settlement_date}"
            )

        if returned_to_mother > 0 and bot.parent_id:
            mother = self.session.get(models.Bot, bot.parent_id)
            if mother is not None:
                mother.capital_operational_usd += returned_to_mother
                self.session.add(mother)
            self.session.add(
                models.FundingEvent(
                    bot_id=bot.id,
                    mother_id=bot.parent_id,
                    amount_usd=-returned_to_mother,
                    funding_type="settlement_return",
                    reason=f"daily settlement {settlement_date}",
                )
            )

        final_equity_usd = bot.capital_operational_usd + bot.reserve_usd

        settlement = models.DailySettlement(
            bot_id=bot.id,
            settlement_date=settlement_date,
            gross_result_usd=gross_result_usd,
            fees_usd=fees_usd,
            interest_usd=interest_usd,
            loan_repayment_usd=loan_repayment_usd,
            returned_to_mother_usd=returned_to_mother,
            retained_operational_usd=retained,
            reserve_contribution_usd=reserve_contribution,
            final_equity_usd=final_equity_usd,
        )
        self.session.add(settlement)
        self.session.add(
            models.AuditLog(
                actor="daily_settlement_engine",
                action="DAILY_SETTLEMENT",
                entity_type="bot",
                entity_id=bot.id,
                details={
                    "settlement_date": settlement_date.isoformat(),
                    "net_result_usd": net_result_usd,
                    "retained_operational_usd": retained,
                    "reserve_contribution_usd": reserve_contribution,
                    "returned_to_mother_usd": returned_to_mother,
                },
            )
        )
        self.session.commit()
        return settlement
