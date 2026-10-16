# Nifty FYERS Algo

Safety-first application for the supplied TradingView Pine strategy. Stages 1–3 provide typed domain objects, fail-closed configuration, durable webhook intake, preserved and versioned Pine source. Stage 4 provides deterministic signal-only CSV replay. Stage 5 adds PAPER-only order management; Stage 6 adds an opt-in FYERS read-only facade; Stage 7 adds only a mocked transaction contract; Stage 8 adds read-only dashboard views. The primary UI is Next.js/React backed by FastAPI; the earlier Streamlit view remains available as an optional fallback. Stage 9 adds persistent shadow-observation instrumentation, but no real shadow run has started and no feeds are connected. No option P&L engine or authenticated FYERS transaction transport exists.

## Safe mode

The application configuration defaults to `PAPER`. Live execution is disabled in code and in `.env.example`; LIVE configuration fails closed. The FYERS read-only client is disabled by default (`NIFTY_ALGO_FYERS_READONLY_ENABLED=false`). No credentials are required to use the current scaffold.

## Setup

Requires Python 3.11 or newer. From the repository root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,test]"
Copy-Item .env.example .env
# Set NIFTY_ALGO_WEBHOOK_SECRET to a random value of at least 32 UTF-8 bytes.
alembic upgrade head
```

Start the API locally (the webhook remains unavailable until a secret is configured):

```powershell
python -m uvicorn nifty_algo.api.app:create_app --factory --env-file .env --host 127.0.0.1 --port 8000 --no-access-log
```

Run tests:

```powershell
python -m pytest
```

Launch the Next.js dashboard locally (loopback only; Node.js 20.9+):

```powershell
Copy-Item frontend/.env.example frontend/.env.local
cd frontend
npm install
npm run dev
```

In another terminal, start FastAPI as above. The Next.js app reads `GET /dashboard/snapshot` from the API at `NEXT_PUBLIC_API_URL` (default `http://127.0.0.1:8000`). The dashboard only reads persisted state; it has no order controls. See [docs/dashboard.md](docs/dashboard.md) for displayed data and limitations. The former Streamlit dashboard can still be launched with `python -m pip install -e ".[dashboard]"` followed by `streamlit run src/nifty_algo/dashboard/app.py --server.address 127.0.0.1 --server.port 8501`.

## Structure

- `src/nifty_algo/api`: FastAPI health, read-only dashboard snapshot, and webhook intake; does not place orders.
- `src/nifty_algo/domain`: typed strategy-independent domain objects and enums.
- `src/nifty_algo/config.py`: configuration and fail-closed mode gate.
- `src/nifty_algo/strategy`: reserved boundary for faithful Pine-rule implementation.
- `src/nifty_algo/backtest`: CSV validation and deterministic signal replay; no fills or order submission.
- `src/nifty_algo/brokers`: broker protocol, network-free PAPER adapter, separate opt-in read-only FYERS facade, and a mocked transaction contract that is not wired into the app.
- `src/nifty_algo/services`: durable PAPER order state manager and signal validation/worker boundaries.
- `src/nifty_algo/data`: SQLAlchemy signal, order, execution, position and audit models, migrations and repositories.
- `src/nifty_algo/dashboard`: read-only persisted-state query layer used by both dashboards.
- `frontend`: Next.js/React operations dashboard.
- `src/nifty_algo/services/shadow_observer.py`: run-scoped typed shadow evidence recorder; it cannot submit orders.

Pine files are under `pine/`; use `mayur_vdbt_rr_v1.pine` for the versioned payload and recreate the TradingView alert after changing scripts (TradingView alerts use a saved script snapshot). Configure `NIFTY_ALGO_WEBHOOK_SECRET` outside source control; redact the secret-bearing endpoint path from logs. The server acknowledges only after committing the event and queue record. `DurableSignalWorker` has no strategy handler wired and cannot submit orders. Install `.[fyers]` only when needed for FYERS reads; set the read-only enable flag and credentials in an untracked local `.env` to create a client. Credentials are not requested in chat, logged, or persisted by the read adapter. See `docs/fyers_readonly.md`.

Signal staleness is not enforced until max age and clock-skew policy are specified, despite v1 carrying timestamps. Duplicate `alert_id` values are idempotently ignored. Historical replay input and limitations are in `docs/backtesting.md`; currently the `data/` directory is empty. Enforce request-rate limits at the public reverse proxy.

Option selection, risk sizing, exit reference, historical option data, and fill assumptions remain unresolved. The Stage 5 order manager accepts only explicit PAPER order requests. FYERS read calls are separate from the mock transaction contract, and no production FYERS transaction transport exists.

The Stage 9 observation tables and dashboard are ready for wiring, but there is no configured signal/quote feed or user-defined run window. See [docs/shadow_operation.md](docs/shadow_operation.md). Stage 10 adds deployment and live-activation readiness documentation and a fail-closed evidence report; no deployment is configured or performed. See [docs/deployment_readiness.md](docs/deployment_readiness.md).

## Security and trading limitations

Do not put broker credentials or access tokens in source control or TradingView alerts. The webhook secret is used in its configured URL path and must be kept out of logs. The project contains no live order implementation. Live trading remains disabled until broker compatibility, hosting, and applicable compliance requirements are verified and separately approved.
