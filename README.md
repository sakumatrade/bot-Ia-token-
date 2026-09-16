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

## Running the Local API

The Local API (spec section 38) requires an explicit API key — with none
configured, every request is rejected (401) rather than running open.

```
cd backend
export BROKER_SAKUMA_LOCAL_API__API_KEY="choose-a-long-random-secret"
uvicorn broker_sakuma.api.app:create_app --factory --port 8765
```

Then, e.g.:

```
curl -H "X-API-Key: choose-a-long-random-secret" http://127.0.0.1:8765/api/dashboard
```

The macOS app's `APIClient` defaults to `http://127.0.0.1:8765`.

## Browser dashboard (works on any OS, no Xcode needed)

With the Local API running (above), open in any browser:

```
http://127.0.0.1:8765/dashboard
```

Paste your API key into "Configurações da conexão" the first time — it's
saved in that browser's `localStorage` only. This is a pragmatic,
cross-platform complement to the native macOS app (which is what the spec
actually asks for): the backend is plain Python and already runs
anywhere, so this page works today without Xcode, a Mac, or any build
step, while the native app remains the primary experience.

## Building the macOS app (on a Mac)

```
scripts/build_mac.sh      # swift build -c release + assembles Broker Sakuma.app
scripts/package_dmg.sh    # packages it into BrokerSakuma.dmg (drag-to-Applications)
scripts/notarize.sh       # signs + notarizes, for distribution beyond this Mac
                           # (needs a paid Apple Developer account — see the
                           # script's header comment for required env vars)
```

These need a real Mac with Xcode/Swift installed; this repository's Linux
CI only proves `swift build`/`swift test` succeed
(`.github/workflows/macos-build.yml`), not that these scripts work — they
haven't been run for real yet. See `docs/PHASES.md`.
