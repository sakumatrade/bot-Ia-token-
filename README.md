# Broker Sakuma

Research, simulation, strategy-management and (eventually, once explicitly
approved) execution platform for crypto opportunities — starting with
Solana/Pump.fun, built to expand to other protocols.

This is a large, safety-critical system built incrementally. See
`docs/ARCHITECTURE.md` for the layered design and `docs/PHASES.md` for what
is built, what is tested, and what is still missing.

## Repository layout

```
backend/    Python 3.12 / FastAPI / SQLAlchemy backend — the system's core.
            Paper trading only until live trading is explicitly enabled.
macapp/     macOS SwiftUI app (source only; requires Xcode/macOS to build —
            see docs/PHASES.md for the environment constraint).
extension/  Safari Web Extension (later phase; no private-key access).
scripts/    Build/packaging scripts (build_mac.sh, package_dmg.sh, notarize.sh).
docs/       Architecture and phase reports.
```

## Backend quickstart

```
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Defaults are conservative: `environment=simulation`,
`trading.live_trading_enabled=false`. Nothing in this codebase can move real
funds; see `docs/ARCHITECTURE.md#security` for why.
