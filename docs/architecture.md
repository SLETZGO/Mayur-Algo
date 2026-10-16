# Architecture (Stages 0–10 readiness)

**Status:** Stages 1–8 implemented; Stage 9 shadow evidence instrumentation is implemented, but no real run has started. Stage 10 provides deployment/live readiness reporting and documentation only. Stage 4 provides data validation and signal-only replay; Stage 5 provides PAPER-only order management; Stage 6 provides FYERS reads; Stage 7 now includes an SDK-backed FYERS transaction transport behind default-off gates, but it is not wired to signal processing or order management; Stage 8 is a read-only dashboard. NIFTY-only option selection, position monitoring, option P&L, and end-to-end order handling remain unimplemented; SENSEX is out of scope.  
**Execution default:** PAPER. Live transaction capability is disabled and uncleared.

## Existing project state

The configured workspace was intentionally empty. Stages 1–3 added typed domain/configuration code, durable webhook intake, preserved and versioned Pine source, and a strict versioned alert contract. Stage 4 adds a CSV data-quality gate and deterministic signal-only replay. Stage 5 adds a broker-neutral protocol, simulated PAPER adapter, persistent order/execution/position records, and restart reconciliation. Stage 6 adds opt-in FYERS reads. Stage 7 adds an SDK-backed FYERS transaction transport behind a false-by-default toggle and an all-false compliance permit; it is not wired to the order manager. Stage 8 adds read-only dashboard queries and UI. Stage 9 adds bounded shadow-run/observation tables and a service, but it is not wired to any incoming signal or quote feed and no real run has started. No historical files are present; there is no option P&L engine or connected FYERS trade path.

## Proposed component boundaries

```text
TradingView Pine indicator
        │ versioned JSON alert over HTTPS
        ▼
FastAPI receiver ── validate/authenticate ── durable database event/queue
                                               │
                                               ▼
                                      signal / strategy logic
                                               │
                                      independent risk checks
                                               │
                        instrument/contract selector (official metadata)
                                               │
                                order and position state manager
                                     │                    │
                           PAPER adapter          FYERS adapter [gated]
                                     │                    │
                                     └──── persistence/audit ──┘
                                               │
                                      Python dashboard
```

### Responsibilities and boundaries

- **Strategy logic:** Pine source is preserved under `pine/`; its indicator-driven rules have a Python signal replay based on exported TradingView series. Replay does not place orders.
- **Historical backtester:** `src/nifty_algo/backtest` validates five-minute CSVs and reproduces setup/next-bar signal events. It does not simulate fills, costs, option contracts, or option P&L; those need confirmed assumptions and option data.
- **FYERS adapter:** `brokers/fyers_readonly.py` is an opt-in SDK facade for explicit data/account reads. `brokers/fyers_transactions.py` has SDK-backed write methods behind a disabled environment toggle and default-deny compliance permit. Neither is connected to signal handling or the order manager. Broker/account risk and deployment compliance remain unverified.
- **Order manager:** `services/order_manager.py` persists explicit order requests and state transitions, deduplicates IDs, records executions and net positions, and reconciles adapter snapshots. It accepts only PAPER mode and a PAPER-marked adapter. It does not infer option selection or map strategy direction to an order side.
- **Database:** SQLAlchemy persists signals, audit events, order intents/states, executions and net positions. Alembic migration `0002_paper_orders` adds Stage 5 order records.
- **Python dashboard:** `dashboard/data.py` contains read-only database queries; `dashboard/app.py` presents status, signals, orders/fills, positions, audit history, health, and config/risk views. Rerenders and refresh only read. Backtest reports are not persisted and are shown as unavailable; no manual order controls exist. Bind locally until deployment authentication is implemented.
- **Shadow observer:** `services/shadow_observer.py` writes typed, run-scoped evidence for signal and feed outcomes, broker quotes, process restarts, proposed contracts, fill estimates, and position comparisons. It has no broker/order dependency, does not choose stale thresholds, contracts, or fills, and is not yet called by feed consumers. User-defined observation window and feed wiring are required before an actual run.
- **Webhook receiver:** implemented at `/webhook/tradingview/{webhook_secret}`; validates legacy and v1 Pine alerts, authenticates, persists, deduplicates and acknowledges without waiting for trade/order processing. V1 includes a millisecond event timestamp, but stale rejection remains disabled until an acceptable age threshold and clock policy are specified. Redact the secret-bearing URL path in access logs.
- **Durable event worker:** generic `DurableSignalWorker` claims persisted events, calls an injected handler, records success, retries failures and dead-letters after a configured attempt count. No handler or worker process is wired into the API; handlers must be idempotent. The worker cannot call FYERS.
- **Deployment edge:** request-rate limiting and log redaction are deployment requirements for any public endpoint; no reverse proxy or public service has been configured.
- **Deployment readiness:** `services/deployment_readiness.py` reports missing evidence references for deployment and live activation. It does not validate evidence, modify configuration, arm live trading, or deploy. No deployment target, approved hosting, static egress IP, or account-specific compliance proof is configured; see `docs/deployment_readiness.md`.

## Instrument units and exits

The v1 contract labels price levels `CHART_SYMBOL` / `CHART_PRICE`. Current scope accepts NIFTY index signals only and intends NIFTY ATM options; those index levels cannot be treated as option premiums. SENSEX support is deferred.

## Safety and compliance boundaries

- BACKTEST/PAPER/SHADOW are the only allowed defaults; live trading is disabled.
- Stage 5 has no networked adapter. Paper orders remain unfilled until a simulated execution is explicitly injected.
- Fail closed on stale data, unknown broker state, ambiguous contract, failed risk check, unavailable persistence, auth/API problems, or incomplete reconciliation.
- Do not interpret API acknowledgement as fill; use documented order/trade updates and reconcile.
- The exact post-2026 regulatory treatment of TradingView → personal Python hosting → FYERS API needs written confirmation from FYERS for this account and deployment topology. No live adapter should be enabled before that and all other compliance checks.
- Keep secrets in environment/secrets management only; do not put secrets in TradingView payloads or logs.
- The dashboard does not expose secret values, database URLs, mutation controls, or broker calls. Signal entry/stop values stay labeled as chart-symbol values; order/fill/position prices are labeled as per-instrument prices.

## Deployment and persistence direction

The master specification suggests PostgreSQL for production and SQLite only for local non-live development. No deployment target, static egress IP, persistence technology, or hosting approval has been established. These choices remain open. Do not deploy an order-originating service based solely on this target diagram.

## Later implementation order

Follow `CODEX_BUILD_PLAN.md`; keep strategy, backtester, broker adapter, order manager, database and dashboard as separate modules. Stages 3–4 have focused tests; option P&L implementation is blocked on source datasets and user decisions, not credentials.
