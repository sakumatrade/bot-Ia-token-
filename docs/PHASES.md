# Phase reports

Repository started empty; nothing was reused or destroyed by definition.

## Phase 0 — Inspection

**Completed.** Repo was empty (no commits, no files). Flagged one hard
environment constraint up front: this container is Linux, so the macOS
app cannot be compiled/packaged here (needs a real Mac + Xcode).

## Phase 1 — Architecture + database + configuration

**Completed.**
- Files: `backend/pyproject.toml`, `backend/src/broker_sakuma/config.py`,
  `backend/src/broker_sakuma/core/enums.py`,
  `backend/src/broker_sakuma/db/{base,models}.py`.
- Features: 31-table SQLAlchemy schema (spec section 45); explicit,
  documented, overridable policy config for risk/loans/settlement/growth
  (nothing financially meaningful hardcoded in logic).
- Tests: `test_config.py`, `test_db_models.py` — 11 tests.
- Known limitations: Alembic migrations not yet wired up (schema is
  created via `Base.metadata.create_all` for now); Postgres not yet
  exercised (tests run against SQLite, which the models are compatible
  with — no Postgres-only types used).
- Security considerations: no secrets in this layer; monetary columns are
  floats for now (a pre-live-trading phase should revisit fixed-point
  Decimal before any real money is at stake).

## Phase 3 — Paper trading

**Completed.**
- Files: `backend/src/broker_sakuma/paper/paper_executor.py`.
- Features: simulated buy/sell with slippage-adjusted price, fees, realized
  P&L, position tracking (weighted-average entry, partial closes), balance
  updates, drawdown tracking via `peak_equity_usd`. Idempotency-key
  protected against double execution.
- Tests: `test_paper_executor.py` — 8 tests, including the duplicate-order
  and insufficient-position edge cases.
- Known limitations: no live executor exists (by design — see spec
  sections 4/61); price/liquidity/slippage inputs are supplied by the
  caller, not yet sourced from a real market-data adapter (that's Phase 11,
  Pump.fun adapter).

## Phase 4 — Risk Engine + Kill Switch + Safe Halt + MaximumLossPolicy

**Completed.**
- Files: `backend/src/broker_sakuma/engines/{risk_engine,max_loss_policy,
  system_state}.py`.
- Features: RiskEngine enforces position size, liquidity, slippage, daily
  loss, trade count, consecutive losses, minimum balance — all as pure,
  independently testable logic gated on the global `SystemState`.
  KillSwitch and SafeHaltManager both persist state as an auditable
  `SystemEvent` row and can never self-clear. MaximumLossPolicy kills a bot
  the instant its configured loss ceiling is breached, mid-trade.
- Tests: `test_risk_engine.py`, `test_system_state.py`,
  `test_max_loss_policy.py`, plus the death-scenario test in
  `test_paper_executor.py::test_bot_dies_after_repeated_losing_trades`
  (spec section 54) — 15 tests.
- Known limitations: RiskEngine currently only guards paper trades; when a
  live executor is built it must route through the exact same
  `RiskEngine.evaluate()` call, not a reimplementation.
- Security considerations: SELL orders (position exits) are deliberately
  exempt from the position-size and minimum-balance floors so a bot can
  never be trapped holding a position it cannot exit — this was caught and
  fixed during test-writing (see git history).

## Next phases (not yet built)

5 (Mother/Son lineage + $5-rule ThesisEngine), 6 (death/post-mortem/
resurrection/collective memory), 7 (loans/interest/daily settlement/
reserve), 8 (learning/backtesting), 9 (bot communication), 10 (research
lab/protocol discovery), 11 (Pump.fun adapter), 12 (wallet manager +
Keychain signer), 13 (Telegram), 14 (Safari extension), 15 (macOS
packaging — requires a Mac), 16 (security hardening pass), 17 (full
integration testing).
