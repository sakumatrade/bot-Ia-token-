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

## Phase 12 — WalletManager + Signer abstraction

**Completed for the backend half; the Keychain-backed half is inherently
macOS-only and not built here.**
- Files: `backend/src/broker_sakuma/engines/{wallet_manager,signer}.py`.
- Features: `WalletManager` handles everything the GUI in spec section 32
  needs — add, rename, activate/deactivate, list (all or active-only),
  update address — all as metadata only. Duplicate `(blockchain,
  public_address)` pairs are rejected; the same literal address string is
  allowed across different blockchains (different address namespaces).
  Changing a **Receiving Wallet**'s address requires an explicit
  `extra_authorization=True` (spec section 34); every other wallet type's
  address can change without it. `Signer` is a `Protocol`; `WatchOnlySigner`
  is the only concrete signer this backend can construct, and it always
  raises `SigningNotPermittedError` — proving the watch-only/signing split
  is a real code boundary, not just a label. Asking for a signer on a
  `SIGNING`-kind wallet raises `SignerNotAvailableError`: this backend
  deliberately has **no** working signer implementation, because a real
  one needs the macOS Keychain, which a Linux backend cannot reach. That
  signer is future work on the Swift side, reached over the Local API only
  once live execution exists (it doesn't yet — trading stays disabled).
  Also added `GET /api/wallets` to the Local API.
- Tests: `test_wallet_manager.py`, `test_signer.py`,
  `test_wallet_model_never_stores_secrets.py` — 12 tests. The last one is
  a structural guarantee, in the same spirit as the LearningEngine AST
  test and the ProtocolStatus enum test: it inspects `Wallet`'s actual
  SQLAlchemy columns and asserts none of them could hold a private key,
  seed phrase, mnemonic, or password — so a secret can't leak into this
  database even by a future developer's mistake, not just by policy.
  148 tests passing overall.
- Known limitations: no Keychain-backed `Signer` exists (can't exist here
  — needs Swift/macOS); no macOS Wallet Manager GUI yet (the SwiftUI app
  from Phase 2 only has the dashboard/menu bar so far); the "never share
  your recovery phrase" warning copy from spec section 34 belongs in that
  future GUI, not the backend.

## Phase 13 — TelegramControlService

**Completed** (control-plane logic + a real Bot API client; the in-app
setup wizard is macOS GUI, not built yet).
- Files: `backend/src/broker_sakuma/engines/telegram_control_service.py`,
  `backend/src/broker_sakuma/adapters/telegram/{__init__,bot_client}.py`.
- Features: roles resolved from `User.telegram_user_id` /
  `User.telegram_role` (new column) — an unrecognized Telegram user, or
  one with no role, is authorized for nothing. All 17 commands from spec
  section 36 are in a fixed `TelegramCommand` enum with a closed
  `COMMAND_PERMISSIONS` map (VIEWER: all read commands; OPERATOR: + pause/
  resume; OWNER: + kill). **Every single attempt** — authorized, denied,
  or unknown-command — writes an `AuditLog` row with the Telegram user ID,
  timestamp, command, confirmation status, reason, and system state at the
  time (spec section 36's exact requirement). `/kill` needs
  `CONFIRM <reason>` in the same call — a bare `/kill` is safely rejected
  and logged as an unconfirmed attempt without touching the system state.
  `/daily` builds the exact field list from spec section 37 (Mother
  Capital, Operational Capital, Reserve, Daily Result, Total Result,
  Active/Dead Bots, Resurrections, New Strategies, New Theses, Capital
  Loaned, Interest, Research, Alerts, System Status) from real queries —
  `build_daily_report()` is reusable independently of the Telegram
  formatting. `TelegramBotClient` wraps the real, public, documented
  Telegram Bot API (`sendMessage`, `getUpdates`) — no business logic, just
  request construction — tested against `httpx.MockTransport`, never a
  real network call.
- **Structural guarantee**: a dedicated AST-based test asserts the control
  service module never imports `subprocess`/`os` and never calls
  `eval`/`exec` — the actual mechanism behind "nunca permitir comandos
  arbitrários do sistema operacional," not just a docstring promise, in
  the same spirit as the LearningEngine and Wallet secret-column tests.
- Tests: `test_telegram_control_service.py`,
  `test_telegram_bot_client.py` — 16 tests. 164 tests passing overall.
- Known limitations: no in-app setup wizard (macOS GUI, not built);
  `TelegramBotClient` is never actually invoked by
  `TelegramControlService` yet — wiring "handle_command() result ->
  send_message()" plus a polling/webhook receiver loop is the next step,
  deliberately left out until there's a real bot token to run it against
  (this repo doesn't have one, and shouldn't invent a fake one to "prove"
  it works end-to-end).

## Phase 14 — Safari Web Extension

**Completed.** Unlike the macOS app, this is plain TypeScript + the
WebExtensions API, so it was written *and* built *and* tested for real
directly in this Linux container — no CI detour needed for that part
(Xcode is only needed for the final native-wrapper conversion step).
- Files: `extension/{manifest.json,package.json,tsconfig.json,popup.html,
  options.html,popup.css}`, `extension/src/{types,apiClient,popup,
  options,background,browser-globals.d}.ts`,
  `extension/tests/structural.test.js`.
- Features: read-only popup (system status, capital, reserve, daily/total
  P&L, active/dead bots) and an options page for the Local API base URL
  and API key. `apiClient.ts` is the **only** module that calls `fetch()`
  — enforced by a test that scans every other source file. `manifest.json`'s
  `host_permissions` are locked to `127.0.0.1:8765`/`localhost:8765`
  only — no `<all_urls>`, no blockchain RPC host, nothing broader — so the
  extension is structurally incapable of reaching a Solana RPC or any
  other endpoint even if compromised. `permissions` is exactly
  `["storage"]`. The options page explicitly warns the user never to
  paste a recovery phrase or private key there (the Local API key it
  actually takes is a different, much lower-stakes credential, and the
  copy says so).
- **Verified for real**: `npm run build` (`tsc`) compiles clean, and
  `npm test` runs `tsc --noEmit` plus structural checks — no blockchain
  SDK import (`@solana/web3.js`, `ethers`, etc.) anywhere in `src/`, no
  reference to private-key/seed-phrase/mnemonic storage anywhere in
  `src/`, `manifest_version: 3`. All 6 checks pass. Also wired into
  `.github/workflows/extension-build.yml` (Node 22 on `ubuntu-latest` —
  no macOS needed for this half) so it's re-verified on every push
  touching `extension/`.
- Known limitations: no native Safari wrapper exists yet — that's
  `xcrun safari-web-extension-converter`, a Mac-only step documented in
  `extension/README.md`; "Abrir Dashboard" currently opens the Local
  API's auto-generated `/docs` page rather than a real dashboard UI or
  the native app (no URL scheme registered for that yet).

## Cumulative test count: 164 Python (`pytest -q` in `backend/`) + 7 Swift
(verified via CI) + 6 TypeScript/structural (`npm test` in `extension/`,
run directly in this environment, not just CI).

## Phase 15 — macOS packaging scripts

**Written, but genuinely unverified — this is the honest state, not a
formality.** This Linux container has no `swift`, `codesign`, `hdiutil`,
or `xcrun`, so none of this could be executed here, only reviewed.
- Files: `scripts/{build_mac.sh,package_dmg.sh,notarize.sh}`,
  `macapp/Resources/Info.plist`.
- `build_mac.sh`: `swift build -c release` then hand-assembles
  `Broker Sakuma.app` (Contents/MacOS + Contents/Resources +
  Contents/Info.plist) — this project is a Swift Package rather than an
  `.xcodeproj`, so there's no Xcode target doing this assembly
  automatically; the script does what Xcode's build phases would.
- `package_dmg.sh`: stages the `.app` plus an `/Applications` symlink and
  calls `hdiutil create` for the standard drag-to-Applications DMG (spec
  section 49).
- `notarize.sh`: `codesign` the app and DMG with a **Developer ID
  Application** certificate, `xcrun notarytool submit --wait`, then
  `xcrun stapler staple`. All four required values (certificate identity,
  Apple ID, team ID, app-specific password) are read from environment
  variables the script `: "${VAR:?...}"`-guards — it refuses to run with
  any of them unset rather than silently skipping a step, and none of
  them are hardcoded or committed anywhere.
- `Info.plist`: includes a narrow `NSAppTransportSecurity` exception for
  exactly `127.0.0.1`/`localhost` (not a blanket
  `NSAllowsArbitraryLoads`), since the app talks to the Local API over
  plain HTTP on the loopback interface only, never the public internet.
  **Validated for real** — not just written — by parsing it with Python's
  `plistlib` in this container to confirm it's well-formed XML the way a
  macOS `Info.plist` needs to be; that's the extent of what's checkable
  without an actual Mac.
- Known limitations / what's still genuinely untested: whether
  `swift build -c release` on a real Mac produces exactly the binary path
  these scripts assume; whether the assembled `.app` actually launches
  (icon is a placeholder — no `AppIcon.icns` exists yet); the entire
  `notarize.sh` flow end-to-end (needs a real paid Apple Developer
  account this project doesn't have). Someone with a Mac needs to run
  `scripts/build_mac.sh` and open the result before this phase can be
  called done rather than "written."

## Phase 16 — Security hardening pass

**Completed**, in the sense a hardening pass should mean: not new
features, but converting manual review findings into permanent,
CI-enforced regression tests.
- Manual review first (documented here since it's real signal, not just
  the tests it produced): grepped the entire backend for
  `eval`/`exec`/`subprocess`/`os.system`, `pickle`/`yaml.load`, raw SQL
  string construction, hardcoded `password`/`api_key`/`secret` literals,
  and `print()`/`TODO`/`FIXME` left behind — all clean. Confirmed every
  one of the four API routers declares `dependencies=[Depends(
  require_api_key)]` and `app.py` defines no bare unauthenticated route.
- Files: `backend/tests/test_security_hardening.py` — turns that review
  into four repo-wide structural tests: (1) no module under
  `src/broker_sakuma` imports `subprocess`/`os` or calls `eval`/`exec`,
  full stop, not just the two modules with their own targeted checks
  (Learning, Telegram); (2) no module anywhere calls `.delete(...)` on
  anything — the append-only guarantee for `audit_logs`/`post_mortems`
  extended to "nothing in this codebase deletes any row from any table";
  (3) no hardcoded secret-shaped assignment (`password = "..."`,
  `api_key = "..."`, etc.) anywhere; (4) **walks the live FastAPI app**
  (not source text) and asserts every included `/api/` route's dependency
  graph actually contains `require_api_key` — this one was deliberately
  verified to have teeth: a route was temporarily stripped of its auth
  dependency, confirmed the test failed, then reverted and confirmed it
  passed again clean.
- Known limitations: this is static/structural hardening, not a
  penetration test or a dependency-vulnerability scan (no network access
  to a CVE database was used); monetary columns are still float, not
  fixed-point Decimal (already flagged in `docs/ARCHITECTURE.md`,
  deliberately not changed here — that's a bigger refactor, appropriately
  scoped to before live trading, not to this pass); rate limiting on the
  Local API was considered and deliberately skipped as low-value for a
  loopback-only, API-key-gated service.

## Phase 17 — Full integration testing

**Completed**, and it earned its keep: it found and fixed a real gap
rather than just re-confirming what the phase-by-phase unit tests already
knew.
- Files: `backend/tests/test_integration.py`,
  `backend/src/broker_sakuma/api/routes/misc.py` (new `/api/protocols`
  route), `backend/src/broker_sakuma/api/schemas.py` (new
  `ProtocolSummary`).
- **What it found**: `CryptoResearchLab` (Phase 10) operates on the
  `protocols` table, but `/api/research` (Phase 38's Local API) only ever
  read from the separate, still-unused `research_reports` table — there
  was no way for the macOS app, the Safari extension, or a Telegram
  `/research` command to ever see protocol research data. Fixed by adding
  `GET /api/protocols`. This is exactly the class of bug isolated unit
  tests structurally cannot catch (each side individually was "correct"
  against its own assumptions) and cross-engine, through-the-API testing
  exists to find.
- Three scenarios, each spanning 5+ engines and verified through the real
  FastAPI `TestClient` rather than direct DB assertions alone:
  1. **Full bot lifecycle**: Mother → Son → $5 thesis → loan-funded
     capital → real `PaperExecutor` trade (through the real `RiskEngine`)
     → `MaximumLossPolicy` death → post-mortem → resurrection → the
     resurrected bot's own thesis still starting at exactly $5 → daily
     settlement → reserve growth → loan repayment — with `/api/dashboard`,
     `/api/bots`, `/api/trades`, `/api/reserves`, and `/api/loans` all
     checked against the state the engines actually produced.
  2. **Discovery → Research Lab**: `PumpFunMonitor` (via
     `MockPumpFunProvider`) registers an opportunity, `ProtocolDiscoveryAgent`
     registers and promotes a protocol to `PAPER_ELIGIBLE` — both
     confirmed via `/api/opportunities` and the new `/api/protocols`.
  3. **Cross-surface kill switch consistency**: a kill switch engaged
     through `TelegramControlService` is immediately visible in
     `/api/status`, blocks `/api/system/resume` (409), and is enforced by
     a completely separate `PaperExecutor` instance — proving Telegram,
     the Local API, and the trading engine all read the exact same
     `SystemState`, not independent copies of it.
- Tests: `test_integration.py` — 3 tests (each substantial: the full
  lifecycle test alone exercises 9 engines/services in sequence).
  171 tests passing overall.
- Known limitations: still no test drives the macOS app or Safari
  extension against a live backend (needs an actual Mac/Safari session,
  as documented throughout); PumpFunMonitor and ProtocolDiscoveryAgent
  integration still uses caller-supplied evidence, since no real external
  data source exists yet (Phase 11's own documented limitation, unchanged
  here).

## Cumulative test count: 171 Python (`pytest -q` in `backend/`) + 7 Swift
(verified via CI) + 6 TypeScript/structural (`npm test` in `extension/`).

## Post-Phase-17 addition — browser-based dashboard

**Not in the original 17-phase plan** — added because the user's real
Mac (Intel MacBook Air, macOS Sequoia 15.7, well below the macOS 26.6 the
current App Store Xcode requires) got stuck mid-setup, and the backend
being plain Python meant a cross-platform fallback was a same-day fix
rather than a redesign.
- Files: `backend/src/broker_sakuma/web/static/index.html`,
  `backend/src/broker_sakuma/api/routes/web.py`.
- Features: a single self-contained HTML/CSS/JS page (no build step, no
  npm) served at `GET /dashboard` (and `GET /` redirects there) — status
  badge, capital/reserve/P&L/bot-count tiles, bot list, alerts list, and
  Pausar/Retomar/Parada de Emergência buttons (kill-switch prompts for a
  reason client-side, matching the API's requirement). It is the exact
  same client pattern as the Safari extension: the API key lives in that
  browser's own `localStorage`, sent as `X-API-Key` on every `/api/*`
  call the page's own JavaScript makes — this route itself serves no
  data, only markup, so it's deliberately **not** behind
  `require_api_key` (verified by `test_dashboard_page_is_public_but_serves_no_data`,
  and the security-hardening route-auth test was narrowed to scope only
  routers actually mounted under `/api`, so this intentional exception
  doesn't silently widen what that test accepts).
- **Verified for real**: started the server with `uvicorn`, curled `/`
  (307 → `/dashboard`) and `/dashboard` (200, no key required, HTML
  references `/api/dashboard` for its actual data rather than embedding
  any).
- Tests: 1 new test in `test_api.py`; `test_security_hardening.py`'s
  route-auth test updated accordingly. 172 tests passing overall.
- Known limitations: no auto-update mechanism yet (spec section 50 is
  still native-app scope); this page is a monitoring/control surface, not
  a replacement for the native app's Simple/Advanced mode split or the
  future setup wizard; it inherits the Local API's single-shared-key auth
  model, so treat that key with the same care as any admin credential.

## Post-Phase-17 addition — macOS app API key bug fix

**Real bug, found live by the user testing on their own Mac**: the
SwiftUI app was written (Phase 2) before the Local API's authentication
existed (added later, in the FastAPI phase), and nothing was ever added
afterward to thread a key through — `APIClient` made every request with
no `X-API-Key` header at all, so every single call 401'd, silently (the
app just showed "disconnected" with no way to explain why).
- Fixed: `APIClient.swift` now takes `apiKey` on every call;
  `AppState.swift` gained a `@Published var apiKey` persisted to
  `UserDefaults`; a new `.missingAPIKey` `APIError` case gives a specific,
  actionable message ("Configure a chave da API em Configurações") instead
  of a generic failure; a new `Views/SettingsView.swift` plus entry points
  (gear icon on the dashboard, "Configurações" in the menu bar) let the
  user actually enter the key.
- Verified via the macOS CI build (green) before telling the user to pull
  and rebuild — same discipline as every other Swift change in this repo.
- This is the kind of gap that only surfaces when a real person runs the
  real app against the real API end-to-end, which is exactly what
  happened here.

## Post-Phase-17 addition — watch-only wallet linking + Telegram profit notifications

Requested directly by the user while testing. Built the parts that are
safe and honest; explicitly declined the parts that aren't (see below).
- **Watch-only wallets**: `POST /api/wallets` (schemas.py:
  `AddWalletRequest`, routes/misc.py: `add_wallet`) always creates a
  `WATCH_ONLY` wallet via the existing `WalletManager` — the request
  schema has no field for a private key, seed phrase, or mnemonic, and
  the handler hardcodes `kind=WalletKind.WATCH_ONLY` regardless of what's
  posted, so there is no way to reach a signing-capable wallet through
  this endpoint even by mistake. Also added a "Carteiras" card to the
  browser dashboard (list + add-by-public-address form), and 4 new API
  tests (duplicate rejection, invalid type rejection, auth requirement).
- **Telegram profit notifications**: new
  `engines/telegram_notifications.py`'s `ProfitNotifier`, built on the
  already-existing `TelegramBotClient` (Phase 13) — sends a message via
  the real Telegram Bot API only when a trade's realized P&L is actually
  positive, and silently no-ops if Telegram isn't configured
  (`enabled`/`bot_token`/`owner_user_id` all required) rather than
  raising. Wired into `PaperExecutor` as an optional constructor
  parameter (`notifier: ProfitNotifier | None = None`, defaulting to
  `None` — fully backward compatible with every existing call site).
  README documents the real setup path: create a bot via
  **@BotFather**, get your numeric user ID via **@userinfobot**, set
  three env vars.
- **Explicitly declined in the same conversation**: the user then asked
  for a way to *send real money to the bot* and *connect a wallet for
  real fund movement, via blockchain APIs*. This was refused, directly
  and with reasons given (spec sections 4/61's explicit "never enable
  live trading automatically"; no real signer exists — see
  `engines/signer.py`; irreversible real-money risk). Recorded here
  because it's a meaningful product-boundary decision, not just a code
  change: this system remains simulation-only, on purpose, and building
  real fund transfer was not something to slip in as a quick follow-up
  request mid-troubleshooting-session.
- Tests: `test_telegram_notifications.py` (6 tests) + 4 new
  `test_api.py` wallet tests. 182 tests passing overall.
- Known limitations: nothing in the running Local API server currently
  *executes* a paper trade (no `POST /api/trades` or similar exists —
  trades only happen via direct engine calls today, e.g. in tests/
  integration scenarios), so `ProfitNotifier` is fully built and tested
  but has no live trigger point yet inside the actual running server;
  wallet linking and Telegram notifications are not yet surfaced in the
  native macOS app (only the browser dashboard), since that would need
  another Xcode CI round-trip not yet done.

## Status: all 17 phases from the original plan have a first pass built.

What's left is exclusively the work that genuinely requires a Mac (the
Wallet Manager GUI, Keychain-backed Signer, Telegram setup wizard, and
native Safari extension wrapper on the SwiftUI side; running
`scripts/build_mac.sh`/`package_dmg.sh`/`notarize.sh` for real; running
the macOS app and Safari extension against a live backend end-to-end) and
integrations that don't exist yet to build against honestly (a real
Pump.fun data source, a real Telegram bot token, a real Solana RPC/signer
for eventual live trading — still structurally disabled throughout). None
of that can be simulated here without violating the spec's own "never
fake a working integration" rule, so it stays documented as exactly that:
not done, not fakeable, waiting on a Mac and on real external
credentials/APIs that don't belong in this repository.

## Post-Phase-17 addition: terminal-friendly bot activation, and keeping the server light

Two more requests came in from the user, both handled entirely inside the
existing safety architecture rather than by adding new escape hatches:

1. **"Activate the bot and give it a wallet with money to work with, all
   from the terminal."** The literal request (a real wallet, real money)
   was declined again, for the same reason as every earlier real-money
   request: no signer exists in this backend (`engines/signer.py`), and
   nothing here can or should move real funds. What was actually
   buildable — and what the user needed — was three curl-friendly
   endpoints on `api/routes/bots.py`: `POST /api/bots/mother` (creates the
   one root bot with a chosen simulated starting balance),
   `POST /api/bots/sons` (spawns a Son under it via the existing
   `LineageEngine`), and `POST /api/bots/{id}/activate` (runs the
   existing `ThesisEngine` state machine through to `INITIAL_TEST` and
   funds it via `BotLoanEngine.create_loan` from the Mother's simulated
   treasury). "Activating" a bot is exactly the $5-rule flow every other
   phase already exercises — `ThesisEngine.start_initial_test` still
   takes no capital argument, so `/activate` has no way to request an
   amount other than $5 even if a caller tries (see
   `test_activate_bot_requires_5_dollars_regardless_of_requested_amount`
   in `tests/test_bot_activation.py`). README.md now has the exact three
   `curl` commands, since the user has consistently preferred terminal
   instructions over Xcode/GUI clicking throughout this project.

2. **"So the server doesn't get too heavy, delete unnecessary files/data
   when a bot dies."** Literal deletion was not built: it would violate
   `test_no_module_anywhere_deletes_a_database_row`
   (`tests/test_security_hardening.py`), a deliberate, CI-enforced rule
   that nothing in this codebase may `DELETE` a row — because a dead
   bot's trade history, lifecycle events and audit trail are exactly what
   `BotPostMortemEngine` and `CollectiveMemoryStore` learn from (spec
   sections 13, 16). Discarding it after death would silently break the
   system's own post-mortem/learning features. What actually keeps the
   server light without losing anything: `db/models.py` gained indexes on
   the columns the growing tables (`paper_trades`, `risk_events`,
   `bot_lifecycle_events`, `funding_events`, `audit_logs`, `alerts`) are
   actually queried by (`bot_id`, `executed_at`/`created_at`,
   `entity_id`, `acknowledged`), and `api/routes/misc.py`'s list
   endpoints (`/trades`, `/alerts`, `/opportunities`, `/research`) now
   accept `?limit=`/`?offset=` (default 200, max 1000) instead of always
   returning every row ever written. Every row a dead bot ever produced
   is still there forever; only a single response's size is bounded.

## Post-Phase-17 addition: P&L chart, and a bot that trades on its own (still simulated)

Two more requests: **"create a chart option for the bot"**, and — in the
same message thread — **"activate Claude so it makes the bot operate
directly, until the end, without needing me."** The second phrasing
echoes the recurring real-money ask this project has declined
consistently (see the section above and every earlier "Post-Phase-17"
entry); this time the buildable, legitimate reading was different:
"operate on its own" as in *not needing a manual command per trade*, not
"connect real money." That distinction mattered enough to build both
readings correctly rather than defaulting to the safest interpretation
by assumption:

1. **P&L chart**: `web/static/index.html` gained a "Gráfico do bot" card
   — pick a bot, see its cumulative simulated P&L plotted as a plain
   inline SVG built from `/api/trades`. No chart library, no network
   dependency, consistent with the dashboard's existing self-contained
   design.

2. **Autonomous PAPER-trading loop**: `adapters/pumpfun/monitor.py`'s own
   docstring had already flagged the actual gap — the pipeline
   deliberately stops at WATCH/IGNORE because *no Strategy component
   existed yet* to turn a WATCH into a concrete, priced order, and
   wiring one in without a real strategy would have been "simulating an
   integration that isn't actually there" (spec section 61). So the
   right fix wasn't to bypass that boundary, it was to build the missing
   piece honestly: `engines/autonomous_trading_cycle.py`'s
   `AutonomousTradingCycle` is a deliberately simple, fully-documented
   placeholder strategy (fixed position sizing, a seeded synthetic exit
   price) that proposes real orders, which still go through the same
   `RiskEngine`/`PaperExecutor`/`MaximumLossPolicy` as every other phase.
   It only ever reacts to `adapters/pumpfun/synthetic_launch_generator.py`'s
   `SyntheticLaunchGenerator` — every mint address it produces is
   prefixed `SYNTHETIC-` and flagged `"synthetic": True` in metadata, so
   nothing downstream can mistake it for real market data. A new
   `AutoTradingConfig` (default `enabled=False`) gates an optional
   background `asyncio` task in `api/app.py`'s lifespan that ticks this
   cycle automatically every `interval_seconds`; `POST
   /api/system/run-cycle` triggers one tick manually regardless. Verified
   end-to-end against a real running server (not just tests): an
   activated bot traded 20 times fully on its own over ~12 seconds with
   zero manual commands, capital moving from the $5 stake up and down
   with real (simulated) P&L, before the test server was torn down.
   `trading.live_trading_enabled` is untouched and still `False` — this
   loop has no path to real money, same as everything else in this repo.

## Post-Phase-17 addition: live controls for the autonomous loop, and a real bug it surfaced

After the autonomous loop above, the user asked (again) for real money —
declined again, same reasoning as every earlier entry — then asked
directly: **"então pra que esse bot serve?"** (then what is this bot
for?). Answered honestly: it's a learning/simulation tool, not a product
that makes real money, and that boundary isn't changing. The user then
asked for "poderes de escolher as opções" (power to choose the options);
clarified via `AskUserQuestion` into three concrete, buildable asks:

1. **A settings panel** for the autonomous loop's parameters.
2. **A live on/off toggle**, no server restart.
3. **Pause/resume individual bots**, independent of the others.

All three landed as pure additions, no new DB migration needed — `core/enums.py`'s
`BotState` already had an unused `PAUSED` value from spec section 64, so
"pause a bot" is just `bot.state = BotState.PAUSED`; `AutonomousTradingCycle
._tradeable_bots()` already only selects `state == ACTIVE`, so a paused bot
is automatically skipped with no change to that engine at all.
`app.py` gained `start_auto_trading()`/`stop_auto_trading()` helpers (used
by both the lifespan startup and the new endpoint) so a request handler
can start or cancel the background `asyncio.Task` live; `GET`/`POST
/api/system/auto-trading` expose that plus the tunable parameters
(`interval_seconds`, `launches_per_cycle`, `position_fraction_of_capital`),
and `POST /api/bots/{id}/pause`/`/resume` handle the per-bot toggle. The
browser dashboard got a matching "Operação automática" card and a
Pausar/Retomar button per bot — and while wiring the dashboard's chart
card from the previous entry, found it had never actually been connected
to `refresh()`/init in that same commit; fixed alongside this.

Writing the tests here caught a real, pre-existing bug:
`MaximumLossPolicy.enforce()`'s `previous_state.value if previous_state
else None` assumed `bot.state` is always a `BotState` enum instance, but
a `Bot` loaded fresh from the database in a new session (exactly what
every API request does, and now what the autonomous loop's background
task does constantly) comes back with a plain Python `str` for that
column — SQLAlchemy doesn't apply an `Enum` type here, just `String(32)`.
`str` has no `.value`, so any bot dying via a fresh session would have
thrown `AttributeError` and turned that request into a 500 (or, in the
background loop, a silently-logged failed cycle) instead of actually
recording the death. `lineage_engine.py`'s `lineage_tree()` already
guarded against exactly this with `hasattr(bot.state, "value") else
bot.state`; `max_loss_policy.py` didn't, and my own first draft of the
pause endpoint copied the same broken pattern. Both now normalize with
`BotState(bot.state) if bot.state else None` before reading `.value`.
Caught by `test_bot_pause_and_auto_trading_control.py`'s pause-then-check
tests, which go through the real `TestClient` (a fresh session per
request) rather than a single shared `db_session` fixture — the same
gap that let the bug through undetected until now.

## Post-Phase-17 addition: genuine pattern learning (still simulated)

After the last entry's live controls, the user again asked for real
money, was declined again, asked "então pra que esse bot serve?" (then
what is this bot for?), and after an honest answer, said (paraphrased):
"the AI is smarter than me, that's why I'm building a bot that learns
patterns... keep building it until it's 100% what I need." Real-money
execution is still declined, same reasoning as every earlier entry — but
"a bot that learns patterns" was a genuine, buildable gap: the
autonomous loop's strategy (previous entry) was deliberately simple and
static, and `learning_engine.py`/`collective_memory.py` already existed
but were never wired into the live decision loop.

Building this honestly required confronting one thing first: the
existing synthetic mock feed produced pure noise (a price walk with no
relationship to anything), so a "learning" system bolted onto it would
have had nothing real to learn — exactly the kind of fake behavior the
spec forbids (section 61), just moved one level down. The fix:
`autonomous_trading_cycle.py`'s synthetic exit-price walk now has an
openly-documented, deliberate bias — more liquidity skews toward a
better outcome — so there's an honest, findable pattern for a learner to
detect, clearly labeled as a mock-feed heuristic, never real market data.

`engines/pattern_learning.py`'s `PatternLearner` is the learner: it
buckets each round trip by liquidity, records the outcome via the
*existing* `CollectiveMemoryStore` (a tagged memory entry — no new
table, no DB migration needed), and returns a confidence multiplier
bounded to `[0.5, 1.5]` once a bucket has at least 5 samples (spec
section 9: one result is a hypothesis, not a fact). `AutonomousTradingCycle
._trade_one` applies that multiplier to the baseline position size,
*then* still clamps against `RiskPolicyConfig.max_position_usd` and the
bot's own capital — the same enforcement order every other phase uses,
so learning can only make a position smaller or modestly larger than the
fixed baseline, never bypass a cap. This mirrors the exact isolation
`learning_engine.py` already established for a different engine (spec
section 7): `pattern_learning.py` has no import of `RiskPolicyConfig`,
`MaximumLossPolicy`, or anything kill-switch-related — it structurally
cannot touch a safety limit even by accident.

Verified end-to-end against a real running server: an activated bot with
$100,000 of Mother capital behind it ran for ~50 seconds with the
autonomous loop on, executed 10 round trips (20 trades) before
`RiskPolicyConfig.max_trades_per_day` (still fully enforced, unmodified)
correctly capped it for the day, and left behind real
`CollectiveMemory` rows tagged by liquidity bucket with genuinely
different outcomes per bucket — not fabricated, the actual recorded
results of that run. 8 new unit tests cover bucket grouping, the
neutral-until-enough-samples rule, and that the multiplier moves in the
right direction (up after positive outcomes, down after negative ones)
and stays bounded regardless of how extreme the outcomes are.

## Post-Phase-17 addition: one script, one update path, and a real bug each surfaced

Two more terminal-convenience requests followed the pattern-learning
work: **"create a button to update the system straight from the code
being built in the cloud"**, then **"create an app with these functions:
update, bot update, automatic API."**

The first request's literal reading — a button *inside* the running
web dashboard or app that pulls from GitHub — isn't something that
should exist: nothing in this codebase may shell out (`import
subprocess`/`os` is forbidden repo-wide by
`test_no_module_anywhere_shells_out_or_evals`), on purpose, because an
API that can run arbitrary commands is a real remote-code-execution
surface, not just an inconvenience to route around. `scripts/update.sh`
is the safe equivalent: one terminal command that does `git pull` (on
whatever branch is currently checked out, not a hardcoded one), reinstalls
the backend, and hands off to `start_server.sh`.

`scripts/start_server.sh` itself also shipped here: it generates an API
key once and persists it to `backend/.local_api.key` (a `*.key` file,
already covered by the existing `.gitignore` pattern — no new ignore
rule needed) so the user never has to `export` it by hand again, and it
frees its own port first (`lsof -ti:$PORT | xargs kill`) instead of
failing with "address already in use," which had come up repeatedly in
this session every time an old server was left running in another
window.

The second request — "an app with these functions" — became
`scripts/broker_sakuma.sh`: a single interactive terminal menu
(update / start-or-check server / create+activate a bot / status /
toggle autonomous trading / open the dashboard) that runs the server as
a background process so the same terminal window stays usable
afterward — removing the "open a second window" step that had caused
confusion multiple times earlier in this session. It's a thin wrapper:
every menu option just calls one of the existing scripts or one `curl`
to an existing endpoint: no new backend code.

Testing it end-to-end (not just reading it) caught a real bug: the menu's
"create and activate a bot" option called `activate_bot.sh` without
passing through its own `$PORT`, so whenever the menu ran on a
non-default port, the child script silently defaulted to 8765 instead,
found nothing listening there, and `activate_bot.sh`'s own `fail_if_error`
— written to expect a numeric HTTP status — crashed on `[ "" -ge 400 ]`
("integer expression expected") under `set -e` with no useful message
at all, just an abrupt stop after the first line of output. Fixed two
ways: the menu now exports `BROKER_SAKUMA_API_URL` to match its own
`$PORT` before calling `activate_bot.sh`, and `activate_bot.sh`'s
`fail_if_error` now checks the code is actually numeric first and prints
"Não consegui conectar em $API_URL — o servidor está rodando?" instead
of crashing silently — a real robustness fix that also helps anyone
running `activate_bot.sh` directly against a server that isn't up yet,
not just this new menu's edge case.

Verified against a real running server through the full menu, not just
individual commands: start in the background, create+activate a bot,
check status, toggle autonomous trading on and confirm it actually
traded (`trades_count` went from 0 to 2), update-and-restart mid-session
and confirm the bot's state survived the restart (same capital and trade
count reappeared after the new server process came up against the same
database file).

## Post-Phase-17 addition: "Criar bot" button in the browser dashboard

The user asked to "create these buttons in the app" right after the
terminal menu shipped — this time meaning the one action from that menu
not yet available as a dashboard button: creating and activating a bot.
`web/static/index.html` gained a "Criar bot" card (name field, Mother's
initial capital field, one button) whose `initCreateBotForm()` does
exactly what `activate_bot.sh` does over `curl`: check for an existing
Mother Bot, create one if missing, spawn a Son, activate it — three
calls to the same `POST /api/bots/mother` / `/sons` / `/{id}/activate`
endpoints from the earlier entry, client-side only, no backend change.
Verified by replaying the exact same three requests via `curl` against a
live server before wiring the JS, confirming the response shapes the
form's error handling and refresh depend on.

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
