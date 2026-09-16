"""SyntheticLaunchGenerator: fabricates clearly-fake launch events so the
autonomous PAPER-trading loop (``engines/autonomous_trading_cycle.py``)
has something to react to, since no real Pump.fun data source is wired
in yet (spec section 61: never simulate a real integration as if it were
functional). This generator does not pretend otherwise anywhere: every
mint address it produces is prefixed ``SYNTHETIC-`` and every launch's
metadata carries ``"synthetic": True``, so nothing downstream (dashboard,
post-mortems, collective memory) can mistake this for real market data.
"""

from __future__ import annotations

import random
import uuid

from broker_sakuma.adapters.pumpfun.provider import LaunchEvent


class SyntheticLaunchGenerator:
    def __init__(self, seed: int | None = None):
        self._random = random.Random(seed)

    def generate(self) -> LaunchEvent:
        token_id = uuid.uuid4().hex[:8]
        liquidity_usd = self._random.uniform(200.0, 5000.0)
        return LaunchEvent(
            mint_address=f"SYNTHETIC-{token_id}",
            symbol=f"SYN{token_id[:4].upper()}",
            name=f"Synthetic Token {token_id[:4].upper()}",
            creator_address=f"synthetic-creator-{self._random.randint(1, 50)}",
            initial_liquidity_usd=liquidity_usd,
            initial_volume_usd=liquidity_usd * self._random.uniform(0.1, 2.0),
            metadata={"synthetic": True},
        )
