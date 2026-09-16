"""ThesisEngine (spec sections 10, 11, 21): the $5 rule.

Every new thesis starts its initial live/paper test with the same small,
fixed amount — regardless of how much capital the bot, or the Mother Bot's
treasury, actually has available. This is enforced structurally: the method
that allocates initial test capital takes no capital argument at all, it
always pulls from ``ThesisPolicyConfig.initial_test_capital_usd``.

Escalation beyond that first test only happens one rung at a time on an
explicit, configured ladder, and only after a thesis has been formally
APPROVED — never from a single lucky trade (spec section 11).
"""

from __future__ import annotations

from broker_sakuma.config import ThesisPolicyConfig
from broker_sakuma.core.enums import BotLifecycleEventType, BotState, InfoClassification, ThesisState
from broker_sakuma.db import models

_ALLOWED_TRANSITIONS: dict[ThesisState, set[ThesisState]] = {
    ThesisState.RESEARCH: {ThesisState.BACKTEST, ThesisState.DISABLED},
    ThesisState.BACKTEST: {ThesisState.PAPER, ThesisState.DISABLED},
    ThesisState.PAPER: {ThesisState.INITIAL_TEST, ThesisState.DISABLED},
    ThesisState.INITIAL_TEST: {ThesisState.VALIDATION, ThesisState.REVIEW, ThesisState.DISABLED},
    ThesisState.VALIDATION: {ThesisState.REVIEW, ThesisState.APPROVED, ThesisState.DISABLED},
    ThesisState.REVIEW: {ThesisState.VALIDATION, ThesisState.APPROVED, ThesisState.DISABLED},
    ThesisState.APPROVED: {ThesisState.DISABLED},
    ThesisState.DISABLED: set(),
}


class ThesisRuleViolation(Exception):
    """Raised when an operation would violate the $5 rule or a state-machine
    invariant of the ThesisEngine."""


class ThesisEngine:
    def __init__(self, session, config: ThesisPolicyConfig):
        self.session = session
        self.config = config

    def create_thesis(self, bot: models.Bot, strategy_version_id: str | None = None) -> models.Thesis:
        if bot.state == BotState.DEAD:
            raise ThesisRuleViolation(f"bot {bot.id} is DEAD and cannot start a new thesis")

        thesis = models.Thesis(
            bot_id=bot.id,
            strategy_version_id=strategy_version_id,
            state=ThesisState.RESEARCH,
            initial_capital_usd=self.config.initial_test_capital_usd,
            current_capital_usd=0.0,
        )
        self.session.add(thesis)
        self.session.commit()
        return thesis

    def _transition(self, thesis: models.Thesis, to_state: ThesisState) -> None:
        current = ThesisState(thesis.state)
        allowed = _ALLOWED_TRANSITIONS[current]
        if to_state not in allowed:
            raise ThesisRuleViolation(f"cannot move thesis from {current.value} to {to_state.value}")
        thesis.state = to_state

    def advance_to_backtest(self, thesis: models.Thesis) -> models.Thesis:
        self._transition(thesis, ThesisState.BACKTEST)
        self.session.add(thesis)
        self.session.commit()
        return thesis

    def advance_to_paper(self, thesis: models.Thesis) -> models.Thesis:
        self._transition(thesis, ThesisState.PAPER)
        self.session.add(thesis)
        self.session.commit()
        return thesis

    def start_initial_test(self, thesis: models.Thesis, bot: models.Bot) -> models.Thesis:
        """Allocate the fixed initial test capital ($5 by default) and move
        the thesis into INITIAL_TEST. This is the only place capital is
        attached to a brand-new thesis, and it never accepts an amount
        parameter — that is the enforcement mechanism for the $5 rule.
        """

        if bot.state == BotState.DEAD:
            raise ThesisRuleViolation(f"bot {bot.id} is DEAD and cannot start a new thesis")

        self._transition(thesis, ThesisState.INITIAL_TEST)
        thesis.current_capital_usd = self.config.initial_test_capital_usd
        self.session.add(thesis)

        bot.theses_tested_count += 1
        self.session.add(bot)

        self.session.add(
            models.BotLifecycleEvent(
                bot_id=bot.id,
                event_type=BotLifecycleEventType.THESIS_STARTED,
                reason=f"thesis {thesis.id} initial test started at ${thesis.current_capital_usd:.2f}",
            )
        )
        self.session.add(
            models.FundingEvent(
                bot_id=bot.id,
                mother_id=bot.parent_id or bot.id,
                amount_usd=thesis.current_capital_usd,
                funding_type="initial_thesis",
                reason=f"$5-rule initial test for thesis {thesis.id}",
            )
        )
        self.session.commit()
        return thesis

    def evaluate_for_validation(
        self,
        thesis: models.Thesis,
        operations_count: int,
        drawdown_pct: float,
    ) -> bool:
        """A single profitable trade is never enough (spec section 11): a
        thesis only becomes eligible for VALIDATION after enough operations
        with acceptable drawdown. Returns whether it advanced.
        """

        if thesis.state != ThesisState.INITIAL_TEST:
            raise ThesisRuleViolation("only a thesis in INITIAL_TEST can be evaluated for validation")

        if operations_count < self.config.min_operations_for_validation:
            return False
        if drawdown_pct > self.config.max_drawdown_pct_for_validation:
            return False

        self._transition(thesis, ThesisState.VALIDATION)
        self.session.add(thesis)
        self.session.commit()
        return True

    def approve(self, thesis: models.Thesis) -> models.Thesis:
        self._transition(thesis, ThesisState.APPROVED)
        self.session.add(thesis)
        self.session.commit()
        return thesis

    def disable(self, thesis: models.Thesis, reason: str) -> models.Thesis:
        thesis.state = ThesisState.DISABLED
        self.session.add(thesis)
        self.session.add(
            models.LearningEvent(
                source_bot_id=thesis.bot_id,
                kind=InfoClassification.REAL_RESULT,
                title=f"Thesis {thesis.id} disabled",
                content=reason,
                related_thesis_id=thesis.id,
            )
        )
        self.session.commit()
        return thesis

    def next_escalation_amount(self, thesis: models.Thesis) -> float:
        """Return the next capital rung for an APPROVED thesis (spec
        section 11). Escalation is one rung at a time on the configured
        ladder; it never jumps straight to a large amount.
        """

        if thesis.state != ThesisState.APPROVED:
            raise ThesisRuleViolation("only an APPROVED thesis may escalate capital")

        ladder = self.config.escalation_ladder_usd
        try:
            current_index = ladder.index(thesis.current_capital_usd)
        except ValueError:
            current_index = -1

        next_index = min(current_index + 1, len(ladder) - 1)
        return ladder[next_index]
