# Codex Build Plan

This plan follows the supplied master specification. Stages 0–8 are implemented, Stage 9's shadow-observation instrumentation is implemented but no real observation run has started, and Stage 10's readiness documentation/checks are implemented without deployment or live activation. Stage 4 has data validation and deterministic signal-only replay, but no actual data/results or option P&L. Stage 5 adds a PAPER-only broker protocol and persistent order/position lifecycle. The initial empty workspace now contains the staged project described below. Proceed one stage at a time and report files, verification commands/results, and unresolved risks after each stage. Do not continue into a risk-sensitive stage without review.

## Stage 0 — Repository and rules discovery (complete)

- Inventory repository, Pine, Python, CSV/data, configuration and tests; subsequently read the supplied Pine attachment.
- Review current official TradingView, FYERS and SEBI/NSE sources; record date, links, findings and account-specific unknowns.
- Create `REPOSITORY_AUDIT.md`, `docs/architecture.md`, `docs/strategy_spec.md`, and this plan.
- Do not add trading code or request credentials.

**Acceptance:** discovery, supplied Pine behavior and current compliance/API findings are documented; no order code is enabled.  
**Result:** accepted for the intentionally empty workspace and supplied Pine attachment. No tests were applicable.

## Stage 1 — Domain models and configuration

- After source discovery, add typed domain/config models and validated BACKTEST/PAPER/SHADOW/LIVE mode gates.
- Ensure PAPER is the safe default and LIVE is rejected for missing limits, compliance readiness, account configuration or explicit arming.
- Add focused tests for configuration and mode gates.

**Result:** implemented with typed domain models, non-secret configuration, and fail-closed live gating. PAPER is the default. Nine standard-library tests pass. No broker or order execution code exists.
**Verification:** `python -m unittest discover -s tests -v` — 9 passed; `python -m compileall -q src tests scripts` — passed; `python -m nifty_algo.main` — starts in PAPER mode without connecting to a broker. The provided bundled Python did not include pytest, so tests use `unittest` (discoverable by pytest after development dependencies are installed).

## Stage 2 — Database and durable signal intake

- Add schema/migrations, FastAPI webhook/health endpoints, validation, authentication, idempotency, durable queue and redacted audit events.
- Acknowledge only after durable persistence; keep request processing within TradingView's three-second limit.
- Test valid, invalid, duplicate, stale and restart cases without broker calls.

**Result:** FastAPI `/health` and `/webhook/tradingview/{webhook_secret}` routes, SQLAlchemy signal/audit tables, Alembic migration, bounded request-body parsing, strict current-Pine payload validation, secret URL authentication, durable queue state, duplicate idempotency, correlation IDs, rejection/duplicate audit records, an explicitly gated recovery operation, and a generic retrying `DurableSignalWorker` are implemented. The worker is not wired to a strategy handler and performs no broker/order calls. Recovery requires an operator to confirm all consumers are stopped; the API does not reset claims automatically because it cannot detect a still-running worker.

**Freshness caveat:** Stage 3 adds a timestamp to v1 alerts, but stale-signal rejection is still deferred until a maximum age and clock-skew policy are specified. Existing legacy payloads remain accepted without timestamps.

**Remaining Stage 2 deployment gate:** configure rate limiting at the public reverse proxy and ensure all server/proxy access logs redact the secret-bearing webhook path before exposing an HTTPS endpoint. No public deployment has been made.

**Verification:** project dependencies installed in `.venv`; `python -m pytest -q` — 21 passed; `python -m compileall -q src tests migrations` — passed; Alembic `upgrade head` — passed on a temporary SQLite database; Alembic reports `0001_signal_intake` as the sole head. One upstream Starlette deprecation warning was reported for `httpx` with its TestClient; tests pass.

## Stage 3 — Pine payload integration

- Inspect the actual Pine source and make only necessary alert integration changes.
- Define a versioned JSON contract with correct reference instrument, units, bar timing and stable signal ID.
- Verify known bars and no repaint/lookahead mismatch; no broker submission.

**Result:** the supplied source is preserved byte-for-byte in `pine/mayur_vdbt_rr_original.pine`; `pine/mayur_vdbt_rr_v1.pine` changes only alert JSON construction. A versioned contract (chart-symbol units, timeframe, bar/emission milliseconds, target) is accepted alongside the legacy six-field payload. No strategy conditions or intrabar/close timing were changed. Python schema tests pass; Pine Editor/runtime verification and end-to-end TradingView alert verification require user validation. Timestamp capture does not enable stale rejection because the age/skew policy is unspecified.

## Stage 4 — Historical replay and option-level backtester

- Validate dataset provenance, coverage, timestamps and gaps.
- Replay signals deterministically, then use contract/time-specific option data for option P&L.
- Model costs, spread, slippage and conservative same-bar ambiguity. Do not call underlying-only results an options backtest.
- Stop option-level claims if reliable option data is unavailable.

**Result:** CSV validation and deterministic signal-only replay are implemented in `src/nifty_algo/backtest`. The input contract requires explicit chart-session dates and TradingView-exported `up_volume`, `down_volume`, and `delta`; replay follows CVD/first-highlight/immediate-next-bar touch rules and outputs event records, not fills. No CSV or options data was supplied, so option P&L, costs, fill modeling, and results are not implemented or claimed. Those require user data and decisions listed in `docs/backtesting.md`.

## Stage 5 — Broker abstraction and paper adapter

- Define broker protocol and simulated paper adapter; build order/position state machine independently of FYERS.
- Test partial fills, rejections, cancellation, ambiguous timeouts, duplicate signals and restart reconciliation.
- Ensure tests cannot call live transaction endpoints.

**Result:** added `BrokerPort`, explicit order request/execution/snapshot types, a network-free `PaperBroker`, and a durable `OrderManager`. The manager accepts only PAPER configuration and adapters, persists intents before submission, treats ambiguous submit/cancel outcomes as reconciliation-required, deduplicates client order/execution IDs, updates partial/complete fill and net-position state, and compares local state with adapter snapshots after restart. Paper fills are injected explicitly; no assumed market fill is generated. Added migration `0002_paper_orders`. No FYERS adapter or transaction code exists; `LIVE` stays disabled.

**Verification:** 43 total tests pass after this stage; Stage 5 includes tests for partial/complete fills, rejection, cancellation, duplicate IDs, ambiguous submit/cancel, missing restart state, unrecorded remote fills, orphan broker state, and PAPER-only adapter gating. Alembic `upgrade head` passed against a temporary SQLite database; compileall passed. A source scan found no FYERS/network order calls in broker/service modules. The paper adapter is in-memory, so after a real process restart it cannot serve as durable broker state; missing snapshots correctly block in `RECONCILIATION_REQUIRED` pending manual review.

## Stage 6 — FYERS read-only connection

- Recheck exact current official FYERS v3 schemas, auth lifecycle, permissions, rate limits, market-data/order streams and plan entitlements.
- Implement only read paths using manually configured credentials when the user is ready; never request or print secrets.
- Reconcile profile, quotes, instrument data, orders, trades and positions; mock network in tests.

**Result:** added `brokers.fyers_readonly` with an opt-in environment gate (disabled by default), secret-redacted credentials/errors, an SDK-lazy read-only facade for profile/funds/holdings/orderbook/tradebook/positions/quotes/history/depth, and an allowlisted public symbol-master loader. The facade does not expose transaction methods and no account connection was made. Optional SDK dependency is `.[fyers]`; tests use fakes/injected symbol-master fetches and make no network calls. FYERS access token remains locally managed; SDK token refresh and session creation are not automated.

**Official docs rechecked:** 2026-10-16. FYERS documents the new app/static-IP activation and says old apps are data-only for quotes, history, order details, positions, and holdings after 2026-04-01; this read-only stage does not establish permission for this deployment topology or any future transaction adapter. Official SDK examples show the method names/argument shapes used here. Current Standard/Prime limits differ by API category; this client does no polling or automatic retries, and deployment must observe the user's actual plan. Account app type, token validity, plan entitlement, exact instrument coverage, and live API behavior remain unverified.

**Verification:** `python -m pytest -q` — 48 passed (one existing Starlette/httpx deprecation warning); `python -m compileall -q src tests migrations` — passed. Stage 6 mocked tests cover opt-in behavior, redaction, whitelist surface, request payloads, symbol-master URL allowlisting and malformed data. No API or symbol-master network calls occurred in tests.

## Stage 7 — Transaction adapter (test-gated; live still disabled)

- Implement documented order/modify/cancel schemas and a fail-closed compliance gate.
- Establish whether this precise personal TradingView-webhook/Python topology is permitted, required hosting, whitelisted static egress IP, new app type/permissions, daily 2FA, order rate/MPP behavior, option data access and any registration/tagging requirements.
- Use sandbox if officially available; otherwise mocked contract tests only. Do not infer a sandbox.
- Do not enable live orders without explicit later approval and completed broker/compliance checks.

**Result:** added `brokers.fyers_transactions` as a mocked, fail-closed transaction contract. It builds documented FYERS v3 order/modify/cancel payloads, requires a complete non-default `FyersCompliancePermit`, allows LIMIT only, redacts transport failures, and treats successful responses as acknowledgements rather than fills. There is no HTTP/SDK write transport, no auth handling, and no connection to `OrderManager` or LIVE mode. No sandbox was inferred or contacted.

**Official checks (2026-10-16):** SEBI framework implementation applies from 2026-04-01 after timeline extension; NSE standards distinguish the sub-10 OPS path (exchange generic algo ID still required) from registered higher-frequency algos, require mapped static IPs, daily logout, auditing and broker RMS. FYERS states daily 2FA, app/IP activation and an order rate limit. NSE FAQ says algo market orders are not permitted; the mock contract therefore supports LIMIT only. NSE's hosting FAQ distinguishes tech-savvy client-hosted logic from vendor platforms hosted by the broker. The exact TradingView-webhook plus user-run Python topology cannot be classified from these generic sources and must be confirmed with FYERS. See `docs/fyers_compliance.md` and `docs/fyers_transactions.md`.

**Verification:** `python -m pytest -q` — 55 passed (one existing Starlette/httpx deprecation warning); `python -m compileall -q src tests migrations` — passed. Contract tests use only an in-memory fake transport; they verify default-deny behavior, limit-only payloads, modify/cancel schemas, invalid terms, secret redaction, and no synthesized fills. All required account and topology confirmations remain unresolved. The current `AppConfig` LIVE gate remains fail-closed; this contract is not a live broker implementation.

## Stage 8 — Python dashboard

- Build status, positions, signals, orders/fills, history/backtest, health/logs and risk/settings views from persisted state.
- Show PAPER/SHADOW/LIVE distinctly and underlying index points separately from option premiums.
- UI rerenders must not submit orders; manual controls require confirmation and audit records.

**Result:** added a read-only Streamlit dashboard with Overview, Signals, Orders & Fills, History & Backtest, Health & Audit, and Risk & Settings views. The query layer loads persisted signal/order/execution/position/audit rows only; no data mutation or broker/service call exists in dashboard code. No manual trading controls are provided. Chart-symbol levels are shown separately from broker instrument prices. Backtest results are explicitly unavailable because Stage 4 has no persisted runs/data. Settings are view-only and secrets/DB URL are hidden. Local loopback launch instructions are documented.

**Verification:** `python -m pytest -q` — 58 passed (one existing Starlette/httpx deprecation warning); `python -m compileall -q src tests migrations` — passed. Dashboard data tests seed SQLite, assert saved-state queries and repeatable reads, and verify a missing-schema/database failure is sanitized. Streamlit is an optional dependency and is not installed in this environment, so the UI server itself was not launched; install `.[dashboard]` to run it locally.

## Stage 9 — Shadow operation

- Observe real signals/quotes with transaction placement disabled.
- Account for duplicates, missed/late signals, feed loss, restarts, proposed contracts/fills and manual position mismatches.
- User defines any observation period; no profitability guarantee is inferred.

**Result:** implemented the prerequisite shadow ledger: migration `0003_shadow_observations`, bounded run records that require an explicit observation end, typed append-only observations for received/duplicate/late/missed signals, quotes, feed gaps, process restarts, proposed contracts, estimated fills and manual position checks/mismatches, plus a read-only dashboard view. Price references are explicit, observations are UTC-normalized, and arbitrary raw JSON/credentials are not accepted. No real run has started: no feeds or account are connected, there is no user-defined observation window, and this ledger is not yet wired to signal/quote consumers. It does not classify stale signals, select contracts, or simulate fills.

**Verification:** `python -m pytest -q` — 62 passed (one existing Starlette/httpx deprecation warning); `python -m compileall -q src tests migrations` — passed; `alembic upgrade head` — passed on an in-memory SQLite database through migration `0003_shadow_observations`. Focused tests cover the shadow event categories, timezone behavior, declared run boundaries, fill-estimate labeling, position mismatch validation, and no order records. Required operational inputs are listed in `docs/shadow_operation.md`.

## Stage 10 — Deployment and optional live activation

- Confirm the exact hosting topology with FYERS and regulatory requirements; configure approved static IP, HTTPS, secrets, supervision, backups and monitoring.
- Run compliance checks and broker reconciliation before processing entries.
- Keep LIVE disabled by default; provide a written checklist and require the user's separate explicit approval before activation.

**Result:** added `docs/deployment_readiness.md` and `services/deployment_readiness.py`, a fail-closed readiness report over named evidence references. Empty references block deployment and live readiness; the report does not configure, deploy, arm, or connect to a broker. Updated the runbook and architecture to reflect the actual Stage 1–10 implementation state. Rechecked official SEBI, NSE and FYERS sources on 2026-10-16. No hosting/account-specific evidence exists, and the exact hybrid TradingView→Python→FYERS topology remains unclassified. No deployment or live activation was performed; LIVE remains disabled and FYERS transaction transport remains absent.

**Verification:** `.venv\Scripts\python.exe -m pytest -q` — 66 passed (one existing Starlette/httpx deprecation warning); `.venv\Scripts\python.exe -m compileall -q src tests migrations` — passed. Focused tests verify empty/partial evidence blocks readiness, complete references only summarize supplied evidence, and unknown/blank evidence keys are rejected. Alembic/migrations unchanged in this stage. `git status` could not run because this workspace has no `.git` repository.

## Permanent architecture constraints

Keep strategy logic, historical backtester, FYERS adapter, order manager, database and Python dashboard separate. Broker success responses are not fills. Never conflate index-point levels with option-premium rupees. Record every decision and keep credentials outside source control. See `REPOSITORY_AUDIT.md`, `docs/architecture.md`, and `docs/strategy_spec.md` for Stage 0 findings.
