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

## Watch-only wallets

`POST /api/wallets` (also in the browser dashboard's "Carteiras" card) adds
a wallet by its **public address only** — there is no field for a private
key, seed phrase, or mnemonic anywhere in this system, and every wallet
added this way is always `WATCH_ONLY`. Nothing here can sign or send a
real transaction; see `docs/ARCHITECTURE.md#security` and
`engines/signer.py` for why that's a structural guarantee, not a policy.

## Telegram profit notifications

To get a message whenever a bot's trade closes with a profit:

1. Message **[@BotFather](https://t.me/BotFather)** on Telegram, send
   `/newbot`, follow the prompts. You'll get a **bot token**
   (looks like `123456789:ABCdefGhIJKlmNoPQRsTUVwxyz`).
2. Message **[@userinfobot](https://t.me/userinfobot)** (or any similar
   bot) to get your own **numeric Telegram user ID** — that's your
   `owner_user_id`/chat ID for a direct message.
3. Set these before starting the backend:
   ```
   export BROKER_SAKUMA_TELEGRAM__ENABLED=true
   export BROKER_SAKUMA_TELEGRAM__BOT_TOKEN="123456789:ABCdefGhIJKlmNoPQRsTUVwxyz"
   export BROKER_SAKUMA_TELEGRAM__OWNER_USER_ID="your-numeric-id"
   ```
4. Open a chat with your new bot and send it any message once (Telegram
   requires the user to message a bot first before it can message back).

Nothing here executes arbitrary commands or touches a wallet — it only
ever sends a plain-text message when `engines/telegram_notifications.py`'s
`ProfitNotifier` sees a trade with positive realized P&L.

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
