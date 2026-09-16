"""LearningEngine (spec section 26): Learning proposes, Policy/Risk decides.

This module deliberately has no dependency on KillSwitch, SafeHaltManager,
RiskPolicyConfig, Settings, wallets, or transfers — that omission *is* the
enforcement mechanism for "Learning nunca pode alterar limites de
segurança / Kill Switch / regras de custódia / limites de transferência /
limites máximos de perda / regras de autorização / políticas de
tesouraria" (spec section 7). See
``tests/test_learning_engine.py::test_learning_engine_has_no_access_to_safety_controls``
for the regression test that keeps it that way.

The one lever LearningEngine has to turn a hypothesis into anything real is
``propose_new_test``, which still only creates a thesis in RESEARCH state
through ``ThesisEngine`` — it has to walk the exact same state machine
(including the $5-only INITIAL_TEST allocation) as any human-initiated
thesis.
"""

from __future__ import annotations

from broker_sakuma.core.enums import InfoClassification
from broker_sakuma.db import models
from broker_sakuma.engines.thesis_engine import ThesisEngine


class LearningEngine:
    def __init__(self, session, thesis_engine: ThesisEngine | None = None):
        self.session = session
        self.thesis_engine = thesis_engine

    def _record(
        self,
        source_bot_id: str | None,
        kind: InfoClassification,
        title: str,
        content: str | None,
        related_thesis_id: str | None,
    ) -> models.LearningEvent:
        event = models.LearningEvent(
            source_bot_id=source_bot_id,
            kind=kind,
            title=title,
            content=content,
            related_thesis_id=related_thesis_id,
        )
        self.session.add(event)
        self.session.commit()
        return event

    def record_fact(self, source_bot_id: str | None, title: str, content: str | None = None) -> models.LearningEvent:
        return self._record(source_bot_id, InfoClassification.FACT, title, content, None)

    def record_observation(self, source_bot_id: str | None, title: str, content: str | None = None) -> models.LearningEvent:
        return self._record(source_bot_id, InfoClassification.DATA, title, content, None)

    def propose_hypothesis(
        self, source_bot_id: str | None, title: str, content: str | None = None, related_thesis_id: str | None = None
    ) -> models.LearningEvent:
        """A hypothesis must never be treated as a fact (spec section 9) —
        hence the distinct classification here versus ``record_fact``."""

        return self._record(source_bot_id, InfoClassification.HYPOTHESIS, title, content, related_thesis_id)

    def compare_strategies(self, metrics_a: dict, metrics_b: dict, metric_key: str = "return_pct") -> dict:
        """Pure comparison, no side effects: returns which of the two
        metrics dicts looks better on ``metric_key`` and by how much. This
        is an opinion, not a decision — nothing here moves a strategy
        state or touches risk policy.
        """

        value_a = metrics_a.get(metric_key, 0.0)
        value_b = metrics_b.get(metric_key, 0.0)
        better = "a" if value_a >= value_b else "b"
        return {"better": better, "metric_key": metric_key, "value_a": value_a, "value_b": value_b}

    def propose_new_test(self, bot: models.Bot, hypothesis_title: str, hypothesis_content: str) -> models.Thesis:
        """Turn a hypothesis into a real (RESEARCH-state) thesis. This is
        the only bridge from Learning to anything resembling money, and it
        still has to pass through ThesisEngine's full state machine — most
        importantly, INITIAL_TEST still only ever allocates the configured
        $5, regardless of what Learning "thinks" the opportunity is worth.
        """

        if self.thesis_engine is None:
            raise RuntimeError("LearningEngine was constructed without a thesis_engine; cannot propose a new test")

        self.propose_hypothesis(bot.id, hypothesis_title, hypothesis_content)
        return self.thesis_engine.create_thesis(bot)
