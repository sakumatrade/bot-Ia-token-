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
scripts/    broker_sakuma.sh is the one command to remember (see below);
            everything else here (build_mac.sh, package_dmg.sh, notarize.sh,
            start_server.sh, update.sh, activate_bot.sh) is what it wraps.
docs/       Architecture and phase reports.
```

## Backend quickstart

The one-command version, safe to re-run any time — creates the virtual
environment if missing, installs everything, and runs the test suite to
confirm it worked:

```bash
./scripts/setup.sh
```

Equivalent by hand:

```
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Defaults are conservative: `environment=simulation`,
`trading.live_trading_enabled=false`. Nothing in this codebase can move real
funds; see `docs/ARCHITECTURE.md#security` for why.

## The easiest way to use everything: one menu

```bash
./scripts/broker_sakuma.sh
```

An interactive terminal menu — no other command to remember, and no
second terminal window needed (it runs the server in the background):

```
1) Iniciar/verificar o servidor
2) Atualizar o sistema (buscar as ultimas novidades)
3) Criar e ativar um novo bot ($5 simulados)
4) Ver status e bots
5) Ligar/desligar a operacao automatica
6) Abrir o painel no navegador
7) Ligar/desligar atualizacao automatica do sistema
0) Sair
```

It's a thin wrapper over `setup.sh`, `start_server.sh`, `update.sh`,
`activate_bot.sh`, `auto_update_loop.sh`, and a couple of `curl` calls to
`/api/system/auto-trading` — everything below in this README works the
same whether you use this menu or run those pieces by hand.

Option 7 checks periodically (every N minutes, your choice) for new
commits on the current branch and updates+restarts automatically when it
finds any — a plain shell script the user runs and can stop at any time,
not something the API can trigger itself: see "Updating to the latest
code" below for why that boundary exists.

## Updating to the latest code

```bash
./scripts/update.sh
```

Pulls whatever has been pushed to your current branch, reinstalls the
backend, and restarts the server (via `start_server.sh` below) — one
command instead of `git pull` + `pip install -e ".[dev]"` + restart by
hand. There is deliberately no "update" button *inside* the running
app/dashboard: nothing in this codebase is allowed to shell out and run
a command like `git pull` (`test_no_module_anywhere_shells_out_or_evals`
forbids importing `subprocess`/`os` anywhere, on purpose — an API able
to run arbitrary shell commands would be a real security hole). This
script is the safe, one-command equivalent you run yourself.

## Running the Local API

The Local API (spec section 38) requires an explicit API key — with none
configured, every request is rejected (401) rather than running open.

The easiest option — one command, no manual `export`, and it frees the
port itself instead of failing with "address already in use" if an old
copy is still running:

```bash
./scripts/start_server.sh              # port 8765 by default
PORT=9000 ./scripts/start_server.sh    # a different port
```

The first run generates an API key and saves it to
`backend/.local_api.key` (git-ignored, never committed) so it's the same
key every time you restart — the script prints it on every run. Stop it
with Ctrl+C; run it again any time, from any state, to restart cleanly.

Equivalent by hand, if you'd rather manage it yourself:

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

If you used `start_server.sh`, every `curl` example in this README that
sets `API_KEY="..."` by hand can instead read the saved key:
```bash
API_KEY="$(cat backend/.local_api.key)"
```

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

Next to the "Broker Sakuma" title, the **☰ Menu** button shows and hides
each section — every card except the main status panel starts hidden,
and clicking a menu entry reveals (and scrolls to) that one, opening
"Configurações da conexão" automatically too. Click the same entry again
to hide it. Below the "modo de testes" banner, a scrolling ticker shows
what the monitor is currently watching in real time — built from
`/api/opportunities` (the same WATCH/IGNORE decisions
`PumpFunMonitor` already records), so it only ever shows genuinely
simulated activity, never anything dressed up as a real market feed.

## Watch-only wallets

`POST /api/wallets` (also in the browser dashboard's "Carteiras" card) adds
a wallet by its **public address only** — there is no field for a private
key, seed phrase, or mnemonic anywhere in this system, and every wallet
added this way is always `WATCH_ONLY`. Nothing here can sign or send a
real transaction; see `docs/ARCHITECTURE.md#security` and
`engines/signer.py` for why that's a structural guarantee, not a policy.

## Creating and activating a bot

The browser dashboard's "Criar bot" card does this with a button: it
creates the Mother Bot if one doesn't exist yet (using whatever simulated
starting capital you enter, only used the first time), spawns a new Son,
and activates it — funding it with the fixed **$5 simulated stake**
(spec section 10's $5 rule). It's a thin client-side wrapper over the
same three endpoints below; no backend change needed to add it.

The native macOS app (`macapp/`) has the same "Criar bot" card, a bots
list with Pausar/Retomar per bot, and a Ligar/Desligar toggle for the
autonomous loop — the same `APIClient` calls as the browser dashboard,
just in Swift. Both surfaces also show a permanent "modo de testes"
banner so it's never ambiguous that nothing on screen is real money.

The native app's header has a button that opens the browser dashboard;
the browser dashboard's ☰ Menu has "Abrir no aplicativo do Mac" going
the other way, via a `brokersakuma://` URL scheme registered in
`macapp/Resources/Info.plist`. That scheme only gets registered with
macOS once the app has actually been launched as a real
`Broker Sakuma.app` bundle (`scripts/build_mac.sh`) at least once — a
plain `swift run` process has no bundle for macOS to register it
against, so the browser-side link may not do anything until you've built
and opened the packaged app once.

## Creating and activating a bot from the terminal

With the Local API running (above), the easiest option is one script that
does everything: creates the Mother Bot if it doesn't exist yet, spawns a
new Son, and activates it (funds it with the fixed **$5 simulated
stake** — spec section 10's $5 rule). No IDs to copy/paste by hand.

```bash
./scripts/activate_bot.sh SUA_CHAVE_DE_API                     # nome do Son automático
./scripts/activate_bot.sh SUA_CHAVE_DE_API "Son 001"           # nome escolhido
./scripts/activate_bot.sh SUA_CHAVE_DE_API "Son 001" 1000      # + capital inicial da Mother (só usado na 1ª vez)
```

Run it again any time to spawn and activate another Son under the same
Mother Bot. It's a thin wrapper over `curl` — see the script itself
(`scripts/activate_bot.sh`) if you want to see exactly what it does.

Everything here is a plain number in this backend's own database; there
is no wallet, private key, or blockchain call anywhere in this flow —
see `docs/ARCHITECTURE.md#security` for why that's a structural
guarantee.

Equivalent step-by-step, if you'd rather run the three `curl` commands
yourself:

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

## Autonomous PAPER-trading loop (bots that trade on their own)

By default, an activated bot only trades when something tells it to
(e.g. `POST /api/system/run-cycle`, or a script calling `PaperExecutor`
directly). To have every `ACTIVE` bot with a started thesis watch and
trade **on its own, with no command needed per trade**, enable the
autonomous loop before starting the backend:

```bash
export BROKER_SAKUMA_LOCAL_API__API_KEY="choose-a-long-random-secret"
export BROKER_SAKUMA_AUTO_TRADING__ENABLED=true
export BROKER_SAKUMA_AUTO_TRADING__INTERVAL_SECONDS=10   # how often it ticks
uvicorn broker_sakuma.api.app:create_app --factory --port 8765
```

Every tick, it generates a handful of clearly-labeled **synthetic** mock
launches (`SyntheticLaunchGenerator` — mint addresses always start with
`SYNTHETIC-`), runs them through the same `PumpFunMonitor` triage as the
rest of the pipeline, and for anything that clears the risk bar, proposes
and executes a small simulated buy/sell round trip through the same
`PaperExecutor` (and therefore the same `RiskEngine` and
`MaximumLossPolicy`) every other phase already uses. A bot can still die
from this — the loop doesn't bypass any safety check, it just removes the
need for you to trigger each trade by hand. See
`engines/autonomous_trading_cycle.py` for the full explanation of why
this can never become live trading (`trading.live_trading_enabled` stays
`False` regardless of this flag) and why it can never be pointed at a
real Pump.fun feed.

### Learning from patterns (still simulated)

Position sizing isn't fixed — `engines/pattern_learning.py`'s
`PatternLearner` buckets every round trip by the launch's liquidity and
remembers each outcome (via the existing `CollectiveMemory` table, no new
schema). Once a bucket has enough samples (5 by default), future trades
in that bucket get a bounded 0.5x–1.5x size adjustment based on how that
bucket has actually performed — a real feedback loop, not a fixed rule,
but still clamped by every existing risk/position limit below it. The
synthetic mock feed deliberately (and openly) correlates liquidity with
outcome so there's an honest pattern to find, not just noise to react to
— see the module's docstring for the full explanation, including the
hard boundary (same one `learning_engine.py` already has) that this can
never touch a safety limit, the kill switch, or the $5 rule itself.

### Turning it on/off live, and adjusting it, without restarting the server

You don't have to set the environment variable above and restart — the
browser dashboard's "Operação automática" card has a Ligar/Desligar
button plus fields for the interval, launches per cycle and position
size, backed by:

```bash
# Check current status
curl -s -H "X-API-Key: $API_KEY" http://127.0.0.1:8765/api/system/auto-trading

# Turn it on (or off), and/or change any of its parameters, live:
curl -s -X POST -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  http://127.0.0.1:8765/api/system/auto-trading \
  -d '{"enabled": true, "interval_seconds": 10, "position_fraction_of_capital": 0.5}'
```

### Pausing one bot without stopping the others

`POST /api/bots/{id}/pause` and `POST /api/bots/{id}/resume` take one bot
in or out of the autonomous loop individually (it just moves the bot to
the existing `PAUSED` state and back to `ACTIVE` — the loop only ever
picks up bots with `state == ACTIVE`). The browser dashboard's "O que o
bot está fazendo" card has a Pausar/Retomar button next to each bot.

```bash
curl -s -X POST -H "X-API-Key: $API_KEY" http://127.0.0.1:8765/api/bots/BOT_ID_AQUI/pause
curl -s -X POST -H "X-API-Key: $API_KEY" http://127.0.0.1:8765/api/bots/BOT_ID_AQUI/resume
```

You can also trigger a single tick manually at any time, loop enabled or
not:
```bash
curl -s -X POST -H "X-API-Key: $API_KEY" http://127.0.0.1:8765/api/system/run-cycle
```

## P&L chart per bot

The browser dashboard (`/dashboard`) has a "Gráfico do bot" card: pick a
bot from the dropdown to see its cumulative simulated P&L plotted over
its trade history — drawn as a plain inline SVG from `/api/trades`, no
external chart library or network dependency.

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
