# Runbook

## Local PAPER development

Requires Python 3.11+. Copy `.env.example` to an untracked `.env`; keep `NIFTY_ALGO_EXECUTION_MODE=PAPER`, `NIFTY_ALGO_LIVE_TRADING_ENABLED=false`, and `NIFTY_ALGO_MANUAL_LIVE_ARMED=false`. A webhook secret is only needed when exercising webhook intake. Apply migrations with `alembic upgrade head`, then bind the API to loopback: `python -m uvicorn nifty_algo.api.app:create_app --factory --env-file .env --host 127.0.0.1 --port 8000 --no-access-log`. `/health` checks database reachability. Do not expose the development server directly to the internet.

The dashboard is read-only and should also bind to loopback. See `docs/dashboard.md`. Apply no live broker credentials in this environment. The FYERS read-only facade is opt-in; no account session is required for local PAPER development.

## Current processing boundaries

The webhook writes an authenticated, validated event to the durable queue. The generic worker is not wired to a strategy handler or started by the API, so this is not an end-to-end trade workflow. Staleness is not rejected until maximum-age and clock-skew policy is selected. Stage 9 observation records are not yet connected to signal or quote consumers and no shadow run has occurred.

`PaperBroker` is an in-memory simulator. It never fetches prices or fills automatically; tests/application code must inject simulated executions. `OrderManager` persists explicit PAPER intents/fills/positions and requires reconciliation after restart. Missing or inconsistent broker snapshots require review. No FYERS transaction transport exists, and no real orders can be placed by the current project.

## Deployment and live activation

No public deployment is configured. Before any endpoint is exposed, complete every deployment gate in `docs/deployment_readiness.md`: written FYERS/exchange topology classification, approved hosting, static egress IP mapping if order-originating, HTTPS/ingress, edge rate limiting and secret-path log redaction, secret storage, production database backup/restore, supervision/monitoring, incident procedures, and reviewed shadow evidence.

Live activation is a separate future change. The current FYERS transaction contract is mocked and disconnected; readiness references do not arm it. Keep PAPER as the execution mode and LIVE disabled. Do not treat a broker acknowledgement as a fill. A future live workflow requires account-specific written broker confirmation, app/IP/authentication setup, exchange algo/tag confirmation, supported instruments/orders, throttling/RMS, risk limits, reconciliation drills, independent compliance review, and the user's separate explicit approval.
