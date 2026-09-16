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

## FastAPI Local API (spec section 38)

**Completed** (the GET/POST surface the spec lists; not yet: rate limiting,
per-caller identity beyond a shared key, or the sensitive-transfer
endpoints, since transfers aren't built yet either).
- Files: `backend/src/broker_sakuma/api/{app,deps,schemas}.py`,
  `backend/src/broker_sakuma/api/routes/{dashboard,system,bots,misc}.py`,
  `backend/src/broker_sakuma/services/{dashboard_service,
  system_control_service}.py`.
- Features: every route requires `X-API-Key`, checked with
  `secrets.compare_digest`; an unconfigured key rejects all requests
  rather than running the API open. `CORSMiddleware` restricts browser
  origins (relevant to a future Safari extension; the native macOS app
  isn't a browser and isn't affected). No cookie-based auth is used, so
  classic CSRF doesn't apply here — documented as a deliberate choice, not
  an omission. `/api/dashboard` and the list endpoints are backed by
  `dashboard_service.build_dashboard_snapshot()`, which aggregates real
  rows (capital, P&L, bot counts, thesis funnel, trade success rate,
  drawdown, unacknowledged alerts) — an empty system legitimately reports
  zeros, never fabricated numbers. `/api/system/{start,pause,resume}` go
  through `SystemControlService`, which refuses to move to ONLINE/PAUSED
  out of EMERGENCY_STOP or SAFE_HALT (409 Conflict) — a generic resume can
  never be what clears a kill switch or safe halt, matching spec section
  29. `/api/system/kill-switch` requires a non-empty `reason` in the body
  (the "operações sensíveis exigem autorização adicional" requirement),
  is reachable from any state, and is idempotent if already engaged.
- Tests: `test_dashboard_service.py`, `test_system_control_service.py`,
  `test_api.py` (full HTTP round-trip via FastAPI's `TestClient`) — 25
  tests. **Also manually smoke-tested for real**: started the server with
  `uvicorn`, hit it with `curl` — confirmed 401 without a key, a real
  `/api/dashboard` response, and a real kill-switch engagement, not just
  mocked/unit-tested behavior.
- Known limitations: single shared-secret auth (no per-Telegram-user or
  per-operator identity yet — `actor` is always recorded as `"local_api"`);
  no endpoint yet to clear EMERGENCY_STOP/SAFE_HALT (intentionally not
  built until there's a properly authorized flow for it); no rate
  limiting; `/api/trades` only returns paper trades (no live `trades` yet,
  since there's no live executor).

## Phase 10 — Research Lab + Protocol Discovery

**Completed.**
- Files: `backend/src/broker_sakuma/engines/{protocol_discovery,
  crypto_discovery}.py`.
- Features: `ProtocolDiscoveryAgent.register_protocol()` is idempotent
  (re-discovering the same name+blockchain returns the existing row) and
  always starts a protocol at `RESEARCH_ONLY`. `compute_risk_score()`
  produces a transparent 0 (safest) to 100 (riskiest) score from evidence
  the schema actually stores — audit count, incident count, age, TVL —
  and deliberately does **not** fabricate the concentration/smart-contract
  sub-scores spec section 24 lists, since we don't collect that data yet;
  inventing a number for it would violate "nunca simular uma integração
  real como se fosse funcional." `update_evidence()` only overwrites
  fields explicitly passed, never backfilling a missing metric with a
  guess. `evaluate_for_paper_eligibility()` requires a risk score to exist
  first and only promotes below a configured threshold.
  **Structural guarantee**: `ProtocolStatus` has exactly four values
  (RESEARCH_ONLY, PAPER_ELIGIBLE, REVIEW_REQUIRED, DISABLED) — there is no
  fifth "approved for live trading" status anywhere in the enum, so
  nothing can "jump straight from discovery to real operation" because
  there's no status value that would even mean that. Tested explicitly.
  `CryptoDiscoveryEngine` logs opportunities across the categories in spec
  section 23 (DEX, DeFi, arbitrage, staking, lending, LP, launchpad,
  yield, infra, cross-chain) and can mark one `IGNORE` with a reason — the
  system is allowed to just not act (spec section 22). `RevenueDiscoveryEngine`
  bridges a "new revenue idea" into both the shared learning feed and a
  tracked opportunity. `CryptoResearchLab.board()` groups protocols by
  status for the dashboard (spec section 25).
- Tests: `test_protocol_discovery.py`, `test_crypto_discovery.py` — 16
  tests. 128 tests passing overall.
- Known limitations: no live data adapters feed `update_evidence()` yet
  (that's Phase 11's Pump.fun adapter and later cross-protocol adapters) —
  today it's only exercised with caller-supplied evidence, same as the
  rest of the research layer until real integrations exist.

## Phase 11 — PumpFunMonitor + MockPumpFunProvider

**Completed.**
- Files: `backend/src/broker_sakuma/adapters/pumpfun/{provider,
  mock_provider,monitor}.py`.
- Features: `PumpFunProvider` is a `Protocol` interface (spec section 3's
  adapter separation) — `PumpFunMonitor` never talks to a data source
  directly. `MockPumpFunProvider` is explicitly, loudly documented as not
  real: it only replays launches the caller pushed into it, and clears
  after each poll like a real feed would, so nothing about its behavior
  could be mistaken for a live integration. The pipeline runs
  New Launch -> Creator Analysis -> Token Analysis -> Liquidity Analysis
  -> Risk Analysis exactly as spec section 22 lists, registering
  creator/token rows idempotently and logging every evaluation as an
  `Opportunity` (classification DATA, category LAUNCHPAD) for the
  Research Lab. **Deliberate scope boundary**: the pipeline only ever
  outputs `WATCH` or `IGNORE`, never `BUY`/`SELL` — spec section 22 also
  says the pipeline ends "Strategy -> Risk Engine -> BUY/SELL/WATCH/
  IGNORE", but wiring straight to a buy/sell decision without a real
  Strategy proposing a concrete, priced order would mean simulating an
  integration (discovery-to-execution) that doesn't actually exist yet —
  precisely what section 61 forbids. A real `BUY`/`SELL` still has to come
  from a Strategy's concrete order going through the already-tested
  `RiskEngine`/`PaperExecutor` from Phase 3-4. A known bad-actor creator
  (flagged via `Creator.risk_notes`) is always `IGNORE`d regardless of
  liquidity.
- Tests: `test_pumpfun_monitor.py` — 8 tests, including one asserting the
  pipeline structurally never returns anything but WATCH/IGNORE. 136 tests
  passing overall.
- Known limitations: no real Pump.fun data source is wired in (none
  exists to wire in — no official public API contract was available to
  implement against); `_analyze_risk` is a simple, transparent rule set
  (flagged creator / high launch velocity / low liquidity), not a learned
  or statistical model.

## Cumulative test count: 136 Python (`pytest -q` in `backend/`) + 7 Swift
(`swift test --package-path macapp`, verified via CI, not run locally).

## Next phases (not yet built)

12 (wallet manager + Keychain signer), 13 (Telegram), 14 (Safari
extension), 15 (macOS *packaging* — .app bundle + .dmg + notarization —
still requires a Mac; CI here only proves the Swift code builds, it does
not assemble or sign a distributable app), 16 (security hardening pass),
17 (full integration testing). The SwiftUI app can now be pointed at a
real, running Local API (see the root README's "Running the Local API"
section) — that wiring (actually running both together end-to-end on a
Mac) still needs to be verified there, since this container can't run the
macOS app itself.

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
