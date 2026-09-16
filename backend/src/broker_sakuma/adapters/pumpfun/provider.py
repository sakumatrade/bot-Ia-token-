"""Provider interface + data shape. Any real integration implements
``PumpFunProvider``; ``PumpFunMonitor`` never talks to a data source
directly, only through this interface (spec section 3's adapter
separation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class LaunchEvent:
    mint_address: str
    symbol: str
    name: str
    creator_address: str
    blockchain: str = "solana"
    initial_liquidity_usd: float | None = None
    initial_volume_usd: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PumpFunProvider(Protocol):
    def fetch_new_launches(self) -> list[LaunchEvent]: ...
