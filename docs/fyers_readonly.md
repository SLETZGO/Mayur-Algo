# FYERS Read-only Integration (Stage 6)

Reviewed against FYERS official sources on 2026-10-16. This is a technical integration boundary, not confirmation that a particular account or deployment is authorized for API use.

## Implemented boundary

`src/nifty_algo/brokers/fyers_readonly.py` is separate from `BrokerPort`, `OrderManager`, and strategy code. It lazily creates the FYERS v3 SDK client and exposes only these documented read calls:

- Profile, funds, holdings
- Orderbook, tradebook, positions
- Quotes, historical candles, market depth
- Public symbol-master JSON from an explicit allowlist

No order placement, modification, cancellation, position exit, or conversion method is exposed. API responses are returned to the calling service but are not logged or persisted by this adapter. SDK exceptions and error payloads are redacted before re-raising.

The Next.js dashboard's Risk & settings page can explicitly check the local session with `POST /fyers/connect`. That route calls only `get_profile()` and returns a connection status; it does not expose profile fields or credentials.

## Enablement and secrets

The client is disabled by default. To create one, configure these in a local, untracked environment only:

```text
NIFTY_ALGO_FYERS_READONLY_ENABLED=true
NIFTY_ALGO_FYERS_APP_ID=...
NIFTY_ALGO_FYERS_ACCESS_TOKEN=...
```

The app secret is not needed by the read client and is not used. No auth flow is automated. The token lifecycle/status must be confirmed using current FYERS account guidance. The client never prints credentials. Install the optional package with `python -m pip install -e ".[fyers]"` when you choose to connect. Constructing a client does not itself make an API request; calls are explicit.

## Documentation and constraints

- FYERS says API apps created under the old setup become data-only from 2026-04-01, allowing quotes, historical data, order details, positions, and holdings while disabling order placement. New app activation requires static IP and selected permissions. [FYERS activation guidance](https://support.fyers.in/portal/en/kb/articles/how-do-i-activate-the-new-app-for-api-trading-after-april-1-2026)
- The FYERS-maintained Python sample initializes `FyersModel` and calls the read methods used here; it also contains write methods, intentionally omitted from this facade. [Official FYERS v3 sample](https://github.com/FyersDev/fyers-api-sample-code/blob/sample_v3/My%20API%20Sample%20Script%28GET%20STARTED%29/Sample_Test_trading_Data.py)
- FYERS-maintained endpoint reference separates GET account/data routes from transaction methods. [Official endpoint catalog](https://github.com/FyersDev/fyers-skills/blob/master/skills/fyers-trading/references/endpoints.md)
- The symbol-master URL pattern and seven accepted segment names are based on FYERS-maintained tooling. Only named master files are accepted, not arbitrary URLs. [Official FYERS symbol tooling](https://github.com/FyersDev/fyers-skills/blob/master/skills/fyers-trading/scripts/fyers_symbols.py)
- FYERS publishes separate Standard and Prime rate limits and data entitlements. This client does not poll or retry, and does not infer the user's plan. Check current limits before adding scheduled reads. [FYERS rate limits](https://support.fyers.in/portal/en/kb/articles/what-are-the-fyers-api-rate-limits-for-standard-and-prime-plans)
- FYERS also documents separate data and order WebSockets. They are not implemented in this stage; before live quote streaming, use the data socket instead of polling quotes, and before order/trade/position event reconciliation, confirm the order socket schema and reconnect behavior. [Official FYERS WebSocket reference](https://github.com/FyersDev/fyers-skills/blob/master/skills/fyers-trading/references/websocket.md)
- Current auth guidance and SDK behavior must be reconfirmed at connection time. The official sample documents auth-code to access-token setup; credentials and access tokens must remain local. [FYERS auth sample](https://github.com/FyersDev/fyers-api-sample-code/blob/sample_v3/v3/python/login/get_access_token.py)

## Not verified / next input

No credentials were requested or used. The user's FYERS app type, activation, permissions, IP, plan, token state, data entitlements, response schemas for their account, and connectivity are unverified. No API network calls occurred in tests. When ready, the user can configure local secrets and run a manual read-only connectivity check; secrets should not be pasted into chat.

This stage does not implement WebSockets, local persistence/reconciliation jobs, auth automation, transaction endpoints, or LIVE enablement. The facade gives later reconciliation work documented read methods but does not yet compare FYERS state against database records. Stage 7 remains a separate compliance and broker-compatibility gate. PAPER remains the execution default and LIVE remains disabled.
