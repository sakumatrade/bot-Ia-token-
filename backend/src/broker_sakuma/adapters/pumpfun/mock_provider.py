"""MockPumpFunProvider (spec section 22): explicitly NOT a real
integration. It never fetches anything from the network — it only returns
launches the caller pushed into it. This exists so the discovery pipeline
can be developed and tested end-to-end before a real, legitimate public
Pump.fun data source is wired in behind the same ``PumpFunProvider``
interface. Never present this provider's output as live market data.
"""

from __future__ import annotations

from broker_sakuma.adapters.pumpfun.provider import LaunchEvent


class MockPumpFunProvider:
    def __init__(self, launches: list[LaunchEvent] | None = None):
        self._launches: list[LaunchEvent] = list(launches or [])

    def push_launch(self, launch: LaunchEvent) -> None:
        self._launches.append(launch)

    def fetch_new_launches(self) -> list[LaunchEvent]:
        launches = list(self._launches)
        self._launches.clear()  # each poll only sees genuinely new launches, like a real feed would
        return launches
