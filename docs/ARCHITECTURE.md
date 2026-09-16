# Architecture

## Layering (spec section 58)

```
SECURITY -> CUSTODY -> TREASURY -> EXECUTION -> RISK -> STRATEGY -> LEARNING
```

A lower layer may never bypass a higher one:

- **Learning** proposes hypotheses and strategy changes. It cannot touch
  Kill Switch, custody, transfer limits, or risk policy.
- **Strategy** proposes orders. It cannot skip the Risk Engine.
- **Risk** (`engines/risk_engine.py`) is a pure decision function: given an
  `OrderRequest` and the current `SystemState`, it approves or rejects.
  Nothing executes without going through it first.
- **Execution** (`paper/paper_executor.py` today; a live executor later)
  only acts on a Risk-approved decision, and itself must respect Custody
  (wallet abstractions — not yet implemented) and Treasury (loan/settlement
  engines).
- **Custody/Security** are enforced structurally: no private key ever
  touches this codebase (see Security below); the Signer abstraction and
  macOS Keychain integration land in the wallet-manager phase.

## Safety primitives

- `engines/system_state.py`: `get_system_state()` derives the global state
  (`ONLINE / PAUSED / SAFE_HALT / EMERGENCY_STOP`) from the latest
  `SystemEvent` row — not in-memory state — so it survives restarts and is
  auditable. `KillSwitch` and `SafeHaltManager` both refuse to self-clear:
  only an explicit call (which the API layer must gate behind owner
  authorization) can reset them.
- `engines/max_loss_policy.py`: every bot carries its own `max_loss_usd`
  ceiling. `MaximumLossPolicy.enforce()` is called after every fill; once
  `cumulative_pnl_usd <= -max_loss_usd`, the bot is transitioned to `DEAD`
  immediately, mid-session — no external process required.
- `engines/risk_engine.py`: position size, liquidity, slippage, daily loss,
  trade count, consecutive losses and minimum balance are all enforced
  before a fill happens. Exiting a position (`SELL`) is never blocked by
  position-size or balance floors, so a bot can never be trapped holding a
  position it cannot exit.

## Paper trading

`paper/paper_executor.py` simulates the full lifecycle of an order: risk
check -> slippage-adjusted fill price -> fee -> position update -> realized
P&L -> drawdown tracking (`Bot.peak_equity_usd` vs current equity) -> max
loss enforcement. All orders require an idempotency key (`PaperTrade
.idempotency_key`, unique at the DB level); replays return the original
trade instead of double-executing.

Live trading is a separate, not-yet-built executor gated by
`Settings.trading.live_trading_enabled` (default `False`). See spec
sections 4 and 61 — this flag must never flip on its own.

## Data model

See `backend/src/broker_sakuma/db/models.py` for the full schema (31
tables per spec section 45): bots, lineage, lifecycle events, wallets,
tokens, creators, protocols, opportunities, trades/paper_trades/positions,
strategies/strategy_versions/backtests, theses, learning_events,
risk_events, treasury, transfers, alerts, **audit_logs** (append-only),
system_events, bot_loans/loan_payments, funding_events, reserves,
**post_mortems** (append-only), collective_memory, daily_settlements,
research_reports.

## Configuration

`backend/src/broker_sakuma/config.py` centralizes every financially
meaningful policy as an explicit, overridable `pydantic-settings` model:
`RiskPolicyConfig`, `MaximumLossPolicyConfig`, `ThesisPolicyConfig`,
`LoanPolicyConfig`, `SettlementPolicyConfig`, `GrowthPolicyConfig`. None of
these numbers are hardcoded inside engine logic (spec sections 19, 57, 62).

## Security

- No seed phrase, private key, or secret is ever stored in code, git, logs,
  or an unprotected database (spec section 33). The wallet-manager phase
  will introduce a `Signer` abstraction backed by the macOS Keychain, with
  an explicit split between watch-only and signing wallets
  (`core/enums.WalletKind`).
- `audit_logs` and `post_mortems` are append-only from the application
  layer: no code path in this repository issues a `DELETE` against them.
- Live trading is disabled by default and structurally separate from the
  paper executor; enabling it is a deliberate, documented, future change —
  not a config flag flipped casually.

## Known environment constraint

This backend is built and tested in a Linux container. The macOS app
(`macapp/`) is authored as real SwiftUI source, organized as an Xcode
project, but **cannot be compiled, run, or packaged into a `.app`/`.dmg`
in this environment** — that requires an actual Mac with Xcode installed.
Anything under `macapp/` should be treated as reviewed-but-unbuilt until
someone opens it on macOS. `scripts/build_mac.sh`,
`scripts/package_dmg.sh` and `scripts/notarize.sh` are written to be run
there, not here.
