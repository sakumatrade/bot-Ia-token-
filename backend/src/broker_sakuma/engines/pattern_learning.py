"""PatternLearner (spec section 26: "Learning propõe, Policy/Risk decide"):
turns each round-trip trade's real (simulated) outcome into a durable
memory the autonomous loop consults *before* its next decision — genuine
learning from accumulated results, not a hardcoded rule.

This reuses ``CollectiveMemoryStore`` as-is (no new table, no DB
migration) — a learned pattern is just a tagged memory entry like any
other, which is also why a human or another engine can inspect what the
bot "believes" via the exact same `find_by_tags` any other memory lookup
uses.

Strict boundary (spec section 7, enforced the same way
``learning_engine.py`` enforces it — by simply never importing these
things): this module has no access to ``RiskPolicyConfig``,
``MaximumLossPolicy``, the kill switch, or the $5 rule. Its only output,
``confidence_multiplier``, is a bounded scalar in ``[0.5, 1.5]`` that the
caller applies *before* the already-existing risk/position caps are
enforced — it can make a position smaller or a little larger within what
was already going to be allowed, never bypass a limit.
"""

from __future__ import annotations

from sqlalchemy import select

from broker_sakuma.core.enums import GrowthSuggestionStatus, InfoClassification
from broker_sakuma.db import models
from broker_sakuma.engines.collective_memory import CollectiveMemoryStore

_LIQUIDITY_BUCKETS_USD = [1000.0, 2000.0, 3500.0, 5000.0]
_PATTERN_TAG_PREFIX = "pattern:liquidity:"


def liquidity_bucket_tag(liquidity_usd: float) -> str:
    """Bucket a launch's liquidity into one of a handful of bands. Buckets
    (not raw liquidity) are the unit of "pattern" here because no two
    synthetic mint addresses ever repeat — only a repeatable *feature* of
    a launch (its liquidity band) can accumulate enough samples to learn
    anything from.
    """

    for edge in _LIQUIDITY_BUCKETS_USD:
        if liquidity_usd < edge:
            low = 0.0 if edge == _LIQUIDITY_BUCKETS_USD[0] else _LIQUIDITY_BUCKETS_USD[_LIQUIDITY_BUCKETS_USD.index(edge) - 1]
            return f"{_PATTERN_TAG_PREFIX}{int(low)}-{int(edge)}"
    return f"{_PATTERN_TAG_PREFIX}{int(_LIQUIDITY_BUCKETS_USD[-1])}-plus"


# One representative liquidity value per bucket `liquidity_bucket_tag` can
# produce — reused instead of duplicating the boundary math, so Dominus
# AI's "what buckets exist" list can never drift from the real buckets.
_BUCKET_SAMPLE_LIQUIDITY_USD = [500.0, 1500.0, 2500.0, 4000.0, 6000.0]


def all_bucket_tags() -> list[str]:
    return [liquidity_bucket_tag(v) for v in _BUCKET_SAMPLE_LIQUIDITY_USD]


class PatternLearner:
    def __init__(self, session, min_samples: int = 5):
        self.session = session
        self.memory = CollectiveMemoryStore(session)
        self.min_samples = min_samples

    def record_outcome(self, bot_id: str, liquidity_usd: float, pnl_usd: float) -> None:
        tag = liquidity_bucket_tag(liquidity_usd)
        self.memory.record(
            source_bot_id=bot_id,
            kind=InfoClassification.REAL_RESULT,
            title=f"round-trip outcome in bucket {tag}",
            content=f"{pnl_usd:.6f}",
            tags=[tag, "pattern:round_trip_pnl"],
        )

    def _samples_for(self, tag: str) -> list[float]:
        entries = self.memory.find_by_tags([tag])
        return [float(e.content) for e in entries if e.content is not None]

    def _multiplier_from_samples(self, samples: list[float]) -> float:
        if len(samples) < self.min_samples:
            return 1.0
        average = sum(samples) / len(samples)
        return 1.0 + max(-0.5, min(0.5, average))

    def confidence_multiplier(self, liquidity_usd: float) -> float:
        """Neutral (1.0) until ``min_samples`` real outcomes exist for
        this bucket — one or two results are never treated as a pattern
        (spec section 26/9: a hypothesis is not a fact). Once there are
        enough, nudge up to 1.5x on a strongly positive average and down
        to 0.5x on a strongly negative one; the caller still clamps the
        result against every existing risk/position limit, so this can
        only ever make a position smaller or modestly larger than the
        fixed baseline, never bypass a cap.
        """

        tag = liquidity_bucket_tag(liquidity_usd)
        return self._multiplier_from_samples(self._samples_for(tag))

    def bucket_insights(self) -> list[dict[str, object]]:
        """Dominus AI: one row per liquidity bucket with at least one real
        (simulated) outcome so far — exactly what feeds
        ``confidence_multiplier``, made visible instead of staying an
        internal detail. Buckets with zero samples are omitted rather than
        padded with fake "no data" rows (spec section 26/9: never claim
        more insight than the evidence actually supports).
        """

        insights: list[dict[str, object]] = []
        for tag in all_bucket_tags():
            samples = self._samples_for(tag)
            if not samples:
                continue
            insights.append(
                {
                    "liquidity_bucket_tag": tag,
                    "samples_count": len(samples),
                    "average_pnl_usd": sum(samples) / len(samples),
                    "confidence_multiplier": self._multiplier_from_samples(samples),
                }
            )
        return insights

    def check_growth_suggestion(self, liquidity_usd: float) -> models.GrowthSuggestion | None:
        """Once a liquidity bucket has enough real (simulated) round trips
        with a clearly positive average, record a ``GrowthSuggestion`` for
        the user to see on the dashboard — this never spawns a bot itself
        (spec section 63: growth is always an explicit human act). Only
        ever suggested once per bucket: if one already exists for this tag
        (pending, dismissed, or acted on), this does nothing, so the user
        is never nagged twice about the same pattern.
        """

        tag = liquidity_bucket_tag(liquidity_usd)
        samples = self._samples_for(tag)
        if len(samples) < self.min_samples:
            return None

        average = sum(samples) / len(samples)
        if average <= 0:
            return None

        already_exists = self.session.execute(
            select(models.GrowthSuggestion.id).where(models.GrowthSuggestion.liquidity_bucket_tag == tag)
        ).first()
        if already_exists is not None:
            return None

        suggestion = models.GrowthSuggestion(
            liquidity_bucket_tag=tag,
            samples_count=len(samples),
            average_pnl_usd=average,
            status=GrowthSuggestionStatus.PENDING,
        )
        self.session.add(suggestion)
        self.session.commit()
        return suggestion
