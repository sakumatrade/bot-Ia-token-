"""BotPostMortemEngine (spec section 13): when a bot dies, its history must
never be silently discarded. This engine is the only writer of
``post_mortems``, and — deliberately — there is no delete/update-cause
removal method here: the table is append-only.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from broker_sakuma.core.enums import BotLifecycleEventType, BotState
from broker_sakuma.db import models


class BotPostMortemEngine:
    def __init__(self, session: Session):
        self.session = session

    def create_post_mortem(
        self,
        bot: models.Bot,
        *,
        probable_cause: str,
        thesis_id: str | None = None,
        strategy_version_id: str | None = None,
        token_id: str | None = None,
        entry_price: float | None = None,
        exit_price: float | None = None,
        slippage_pct: float | None = None,
        liquidity_usd: float | None = None,
        market_condition: str | None = None,
        failed_hypothesis: str | None = None,
        rule_that_should_have_prevented: str | None = None,
    ) -> models.PostMortem:
        if bot.state != BotState.DEAD:
            raise ValueError(f"post-mortem can only be created for a DEAD bot, bot {bot.id} is {bot.state}")

        post_mortem = models.PostMortem(
            bot_id=bot.id,
            thesis_id=thesis_id,
            strategy_version_id=strategy_version_id,
            token_id=token_id,
            entry_price=entry_price,
            exit_price=exit_price,
            slippage_pct=slippage_pct,
            liquidity_usd=liquidity_usd,
            market_condition=market_condition,
            probable_cause=probable_cause,
            failed_hypothesis=failed_hypothesis,
            rule_that_should_have_prevented=rule_that_should_have_prevented,
        )
        self.session.add(post_mortem)
        self.session.add(
            models.BotLifecycleEvent(
                bot_id=bot.id,
                event_type=BotLifecycleEventType.POST_MORTEM_CREATED,
                reason=probable_cause,
            )
        )
        self.session.commit()
        return post_mortem

    def confirm_cause(self, post_mortem: models.PostMortem, confirmed_cause: str) -> models.PostMortem:
        """Add a confirmed cause once investigated further. This updates the
        existing row in place (never deletes it) — the probable_cause and
        every other original field stay intact for the audit trail.
        """

        post_mortem.confirmed_cause = confirmed_cause
        self.session.add(post_mortem)
        self.session.commit()
        return post_mortem
