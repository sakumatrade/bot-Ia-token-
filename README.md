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

## Creating and activating a bot from the terminal

With the Local API running (above), these three `curl` commands create the
Mother Bot, spawn a Son under it, and "activate" that Son — funding it with
the fixed **$5 simulated stake** (spec section 10's $5 rule) from the
Mother Bot's own simulated treasury. Everything here is a plain number in
this backend's own database; there is no wallet, private key, or
blockchain call anywhere in this flow — see
`docs/ARCHITECTURE.md#security` for why that's a structural guarantee.

```bash
API_KEY="choose-a-long-random-secret"   # same value you started uvicorn with

# 1. Create the Mother Bot once, with however much simulated starting capital you want.
curl -s -X POST http://127.0.0.1:8765/api/bots/mother \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"name": "Mother Bot", "initial_capital_usd": 1000}'

# 2. Copy the "id" field from that response, then spawn a Son under it.
curl -s -X POST http://127.0.0.1:8765/api/bots/sons \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"parent_id": "PASTE-THE-MOTHER-ID-HERE", "name": "Son 001"}'

# 3. Copy the Son's "id", then activate it — this starts its first thesis at $5.
curl -s -X POST http://127.0.0.1:8765/api/bots/PASTE-THE-SON-ID-HERE/activate \
  -H "X-API-Key: $API_KEY"
```

After step 3, `curl -H "X-API-Key: $API_KEY" http://127.0.0.1:8765/api/bots`
or the browser dashboard at `/dashboard` will show the Son as `ACTIVE`
with `capital_operational_usd: 5.0`. There is no field anywhere in these
endpoints to request a different starting amount — the $5 rule is
enforced by `ThesisEngine.start_initial_test`, which takes no capital
argument at all.

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

## Data retention: nothing is ever deleted

When a bot dies, its full trade history, lifecycle events and audit trail
stay in the database forever — that history is exactly what the
post-mortem and collective-memory features (spec sections 13, 16) learn
from, and `test_no_module_anywhere_deletes_a_database_row` (in
`tests/test_security_hardening.py`) enforces this as a permanent,
CI-checked rule: no code path anywhere in this codebase may issue a
`DELETE`. So the server stays fast as history grows a different way —
without discarding anything:

- List endpoints that can grow without bound (`/api/trades`, `/api/alerts`,
  `/api/opportunities`, `/api/research`) accept `?limit=` and `?offset=`
  query parameters (default `limit=200`, max `1000`) instead of always
  returning every row ever written.
- The database tables most bots write to repeatedly (`paper_trades`,
  `risk_events`, `bot_lifecycle_events`, `funding_events`, `audit_logs`,
  `alerts`) are indexed on the columns those queries actually filter by
  (`bot_id`, `executed_at`/`created_at`), so lookups stay fast regardless
  of how many bots have died.

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
