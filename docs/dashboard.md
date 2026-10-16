# Read-only operations dashboard (Stage 8)

The primary web UI is a Next.js/React dashboard in `frontend/`. It reads application tables through `GET /dashboard/snapshot`, backed by `dashboard.data`. The endpoint is read-only and does not call `OrderManager`, a broker adapter, strategy code, or any transaction endpoint. Browser rerenders and the refresh button only repeat database reads. There are no editable controls or order actions. The legacy Streamlit dashboard remains available and uses the same query layer.

Start FastAPI on loopback as described in the README. Then launch the Next.js dashboard locally (Node.js 20.9+):

```powershell
Copy-Item frontend/.env.example frontend/.env.local
cd frontend
npm install
npm run dev
```

`NEXT_PUBLIC_API_URL` selects the FastAPI base URL and defaults to `http://127.0.0.1:8000`. FastAPI CORS is limited to the local Next.js origins `http://localhost:3000` and `http://127.0.0.1:3000`; update this allowlist explicitly for a future deployment. The endpoint returns safe configuration metadata only and never returns webhook secrets or database URLs.

The Risk & settings view has an explicit **Check connection** action. To create/update the local access token, install the optional FYERS SDK (`python -m pip install -e ".[fyers]"`) and run `python scripts/fyers_login.py` from the repository root. It prompts for App ID, the App Secret (hidden), and the exact registered redirect URL, opens FYERS login for the user's daily verification, then accepts the auth code or full redirected URL as hidden input. It stores the App ID, access token, and read-only enable flag in the ignored local `.env`; the App Secret and auth code are not written or printed. Restart FastAPI using `--env-file .env`, then use **Check connection**. This validates only one FYERS profile read and does not enable order placement. Rotate any secret previously exposed in screenshots before running the helper.

Install the optional dashboard dependency and launch locally:

```powershell
python -m pip install -e ".[dashboard]"
streamlit run src/nifty_algo/dashboard/app.py --server.address 127.0.0.1 --server.port 8501
```

Views cover execution status, persisted signals, orders and executions, current persisted positions, audit history, database health, and current in-memory configuration/risk limits. Secret values and database URLs are never displayed. `health` in the dashboard refers to its own process and database connectivity; audit rows are not host/server logs.

Pine entry/stop prices are labeled as chart-symbol prices (index values are index points). Order, fill and position average prices are per broker instrument. The UI does not infer that an instrument price is an option premium; use the symbol metadata to identify it. Never compare those prices directly to underlying index-point levels.

No backtest results are persisted in the present project. Stage 4 replay currently emits in-memory signal events only and no CSV/options dataset has been supplied. The dashboard says so rather than creating synthetic P&L. Risk/settings are view-only and reflect `AppConfig` values; risk settings are not presently persisted or editable in the dashboard.

Until deployment authentication and network controls are implemented, bind the API and dashboard to loopback (`127.0.0.1`) and do not expose them publicly. PAPER remains the configured mode by default, and the UI cannot activate LIVE.
