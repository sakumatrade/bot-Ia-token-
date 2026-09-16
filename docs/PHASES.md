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

## Phase 5 — Mother Bot + Son lineage + ThesisEngine ($5 rule)

**Completed.**
- Files: `backend/src/broker_sakuma/engines/{lineage_engine,thesis_engine}.py`.
- Features: `LineageEngine` creates the Mother Bot and spawns Son bots with
  full lineage rows, lifecycle events and audit logs; enforces
  `max_bots`/`max_generations` from `GrowthPolicyConfig`; exposes a
  `lineage_tree()` view. `ThesisEngine` implements the full state machine
  (RESEARCH -> BACKTEST -> PAPER -> INITIAL_TEST -> VALIDATION -> REVIEW ->
  APPROVED -> DISABLED) and — the load-bearing rule — `start_initial_test()`
  takes no capital argument at all, so it can only ever allocate
  `ThesisPolicyConfig.initial_test_capital_usd` ($5 by default), regardless
  of how much the Mother Bot's treasury holds. Escalation only moves one
  rung at a time on an explicit ladder, and only once APPROVED.
- Tests: `test_lineage_engine.py`, `test_thesis_engine.py` — 14 tests,
  including one that explicitly funds Mother with $5,000,000 and asserts
  the next thesis still gets exactly $5.
- Known limitations: son auto-naming is a flat counter (`Son 003`), not the
  letter-branch scheme shown illustratively in the spec (`001-A`); callers
  can still pass an explicit name to get that shape by hand.

## Phase 6 — Death + Post-mortem + Collective Memory + Resurrection

**Completed.**
- Files: `backend/src/broker_sakuma/engines/{post_mortem_engine,
  collective_memory,resurrection_engine}.py`.
- Features: `BotPostMortemEngine` creates an append-only post-mortem
  (only for a bot already `DEAD`) capturing entry/exit price, slippage,
  liquidity, market condition, probable cause, failed hypothesis, and the
  rule that should have prevented the loss; `confirm_cause()` updates in
  place, never replacing the original record. `CollectiveMemoryStore`
  records classified knowledge (`InfoClassification`) and can be queried
  by tag. `BotResurrectionEngine` spawns a new versioned bot
  (`Son 017` -> `Son 017-R1` -> `Son 017-R1-R1`, ...) whose lineage row
  carries `previous_failure`/`correction`, and records both the failure and
  the correction into collective memory.
- Tests: `test_post_mortem_and_memory.py`,
  `test_resurrection_engine.py` — 7 tests, including a full
  death -> post-mortem -> resurrection -> new-$5-thesis cycle (spec
  section 54) and a double-resurrection version-suffix check.
- Known limitations: resurrection is triggered explicitly by a caller
  (e.g., an operator or a future automated learning step), not
  auto-triggered the instant `MaximumLossPolicy` kills a bot — post-mortem
  creation is deliberately a separate, explicit step so a human/learning
  process supplies `probable_cause`/`correction` rather than the system
  guessing at them.

## Phase 7 — Loans + Interest + Daily Settlement + Reserve

**Completed.**
- Files: `backend/src/broker_sakuma/engines/{loan_engine,
  loan_interest_engine,daily_settlement_engine,reserve_growth_engine}.py`.
- Features: `BotLoanEngine` enforces Mother's exposure ceiling
  (`LoanPolicyConfig.mother_max_total_loan_pct_of_treasury`, e.g. Mother
  with $1,000 and a 20% limit can never have more than $200 outstanding —
  spec section 57) and records loans/payments with full balance tracking.
  `BotLoanInterestEngine` implements FIXED/PROFIT_SHARE/HYBRID models;
  PROFIT_SHARE and the profit-linked half of HYBRID floor at zero on a
  loss (never invents profit). `DailySettlementEngine` splits a profitable
  day's net result across retained-operational/reserve/returned-to-Mother
  using explicit configured percentages, and never distributes a loss into
  reserve or Mother — it's carried entirely as reduced operational
  capital. `ReserveGrowthEngine` is the single source of truth for a bot's
  (or Mother's) reserve balance, separate from operational/borrowed
  capital.
- Tests: `test_loan_engine.py`, `test_settlement_and_reserve.py` — 14
  tests, including the exact $1,000/20%/$200 exposure scenario (section
  57), the $100-loan/$20-profit/profit-share-interest scenario (section
  56), and a two-day reserve-accumulation test proving a new thesis still
  starts at $5 even with a large reserve (section 55).
- Known limitations: `DailySettlementEngine.settle()` takes
  `gross_result_usd` as a caller-supplied number rather than aggregating
  it itself from `paper_trades`/`trades` for the day — that aggregation
  belongs in the scheduler/API layer built in a later phase, once there's
  an actual daily cron to drive it.

## Phase 8 — Learning Engine + Backtest Engine

**Completed.**
- Files: `backend/src/broker_sakuma/engines/{learning_engine,
  backtest_engine}.py`.
- Features: `LearningEngine` can record facts/observations, propose
  hypotheses (classified separately from facts per spec section 9), give a
  pure opinion comparing two strategies' metrics, and turn a hypothesis
  into a new RESEARCH-state thesis — but that's its ceiling: the module has
  zero imports of `KillSwitch`, `SafeHaltManager`, `RiskPolicyConfig`,
  `RiskEngine`, `Transfer`, `Wallet`, or `Settings`, which is the actual
  enforcement mechanism for "Learning nunca pode alterar limites de
  segurança" (section 7), not just a docstring promise. `BacktestEngine`
  versions strategies through RESEARCH -> BACKTEST -> PAPER -> REVIEW ->
  APPROVED -> DISABLED, enforces strict, non-overlapping TRAIN/VALIDATION/
  TEST date windows before any run starts (`LookAheadBiasError` otherwise),
  and trims any data point outside a split's own window before the
  strategy function ever sees it — so a caller literally cannot leak
  future data into a backtest even by mistake. Promotion to PAPER requires
  at least one TEST-split backtest already on record.
- Tests: `test_learning_engine.py`, `test_backtest_engine.py` — 12 tests,
  including an AST-based structural test that asserts LearningEngine's
  module never imports any of the forbidden safety-control symbols (this
  is a regression test, not just documentation — it will fail the moment
  someone adds a `from broker_sakuma.engines.risk_engine import RiskEngine`
  to that file).
- Known limitations: `BacktestEngine` orchestrates versioning and the
  TRAIN/VALIDATION/TEST invariants but does not itself simulate a market —
  the actual trading-logic function is supplied by the caller
  (`strategy_fn`). Overfitting can be discouraged structurally (requiring
  TEST-split evidence before promotion) but not fully prevented by code
  alone; that still needs human review at the REVIEW state.

## Phase 9 — BotCommunicationEngine + BotCouncil

**Completed.**
- Files: `backend/src/broker_sakuma/engines/bot_communication.py`.
- Features: `BotCommunicationEngine.broadcast()` shares classified intel
  between bots (reuses the `LearningEvent` table rather than adding a
  parallel one — it already has the right shape); `verified_ground_truth()`
  returns only FACT/DATA/REAL_RESULT, deliberately excluding HYPOTHESIS,
  SIMULATION and AGENT_OPINION. `BotCouncil.convene()` tallies multiple
  bots' opinions into a majority verdict — but that verdict is always
  recorded back as `AGENT_OPINION`, never `FACT`, no matter how many bots
  agreed (spec section 9's core rule, tested explicitly).
- Tests: `test_bot_communication.py` — 7 tests. 87 tests passing overall.

## Phase 2/15 (partial) — macOS SwiftUI app, built and verified in the cloud

**Completed for what's in scope so far (dashboard + menu bar shell); wizard,
wallet manager UI, Telegram UI, Safari extension still pending.**
- This container is Linux and cannot run Xcode. There is also no "Xcode
  online" product from Apple — the practical equivalent used here is
  **GitHub Actions' `macos-14` runners**, which ship a real Xcode/Swift
  toolchain. `.github/workflows/macos-build.yml` builds (debug + release)
  and tests the app on every push touching `macapp/`.
- The app is a **Swift Package** (`macapp/Package.swift`), not a
  hand-written `.xcodeproj` — a hand-crafted `project.pbxproj` is fragile
  without Xcode itself to generate it, whereas `swift build`/`swift test`
  and Xcode's own "open Package.swift" both work directly against this
  layout on a real Mac.
- Files: `BrokerSakumaApp.swift` (menu bar + dashboard window scenes),
  `AppState.swift` (polling, never keeps stale data on a failed refresh),
  `APIClient.swift` (talks to the future Local API, never fabricates a
  response), `DashboardModels.swift`, `BeginnerError.swift` (spec section
  43: plain-language headline, technical detail behind a toggle, never a
  raw HTTP code), `Views/DashboardView.swift` (Simple/Advanced mode,
  metrics grid), `Views/MenuBarContentView.swift` (Pause/Resume/Emergency
  Stop with a confirmation dialog on the destructive action, per spec
  section 40).
- **Verified green for real**, not just "should compile": run
  https://github.com/sakumatrade/bot-Ia-token-/actions/runs/35139777485 —
  debug build, 7 Swift unit tests (all passing), and a release build all
  succeeded on GitHub's actual Apple toolchain. The release binary is
  downloadable from that run's artifacts
  (`broker-sakuma-macos-binary`) — but it only runs on macOS; there is no
  Windows target because SwiftUI/AppKit are Apple-only.
- Known limitations: the app has no real data to show yet (the Local API
  it talks to doesn't exist — Phase not started), no setup wizard (section
  41), no Wallet Manager UI, no Telegram UI, no manual/help content
  (section 42), no menu items beyond Pause/Resume/Emergency Stop/Quit. It
  correctly shows a "disconnected" beginner-friendly state rather than
  fabricating dashboard numbers while the API is missing.

## Cumulative test count: 87 Python (`pytest -q` in `backend/`) + 7 Swift
(`swift test --package-path macapp`, verified via CI, not run locally).

## Next phases (not yet built)

10 (research lab/protocol discovery), 11 (Pump.fun adapter), 12 (wallet
manager + Keychain signer), 13 (Telegram), 14 (Safari extension), 15
(macOS *packaging* — .app bundle + .dmg + notarization — still requires a
Mac; CI here only proves the Swift code builds, it does not assemble or
sign a distributable app), 16 (security hardening pass), 17 (full
integration testing), plus the FastAPI Local API (section 38) that the
SwiftUI app is written to call but doesn't exist yet.

## macOS app — what the user needs to do on their own Mac

Compiling in CI proves the code is correct; it does not give you a
double-clickable `.app`. To actually run it locally or produce a signed
`.dmg`, on an actual Mac:

1. **Xcode** (Mac App Store, free) or at minimum the Command Line Tools
   (`xcode-select --install`).
2. A normal Apple ID signed into Xcode (Settings -> Accounts) — sufficient
   for local, unsigned builds/runs on that same Mac.
3. Only if distributing the `.dmg` outside the Mac App Store without a
   Gatekeeper warning (spec section 49): an Apple Developer Program
   enrollment (developer.apple.com, paid), a **Developer ID Application**
   certificate generated from Xcode, and an app-specific password for
   `notarytool` — supplied to `scripts/notarize.sh` via environment
   variables/CI secrets, never committed to git.
4. `git pull origin claude/broker-sakuma-macos-app-d17bns`, then
   `cd macapp && open Package.swift` (Xcode opens it as a Swift Package)
   and run with ⌘R, or `swift run` from the terminal.
