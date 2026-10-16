# FYERS Transaction Contract (Stage 7)

## Stage boundary

`src/nifty_algo/brokers/fyers_transactions.py` encodes FYERS v3 place, modify, and cancel requests and now includes an SDK-backed transport. The transport requires `NIFTY_ALGO_FYERS_TRANSACTIONS_ENABLED=true`, an App ID, and an access token. Every write still passes the explicit `FyersCompliancePermit`, which defaults to denying every operation. The transport is not constructed by the app, signal worker, or dashboard and does not connect an alert to an order. The PAPER `BrokerPort` and `OrderManager` remain separate and unchanged.

## User-requested execution flow (not implemented)

The operator has requested this flow for a future integration:

1. Hold each TradingView signal for dashboard review. Before entry, the operator chooses 1–50 lots. Only NIFTY index signals are accepted.
2. LONG buys the selected index's nearest-expiry ATM CE; SHORT buys its nearest-expiry ATM PE.
3. Entry, initial stop, and the 1R breakeven trigger use the NIFTY index levels in the signal. At +1R, the index stop moves to the entry level. The remaining target exit is manually initiated from the dashboard.
4. Close any open option position at 15:00 Asia/Kolkata time.

Only NIFTY is in scope now; SENSEX support is deferred. An index price level cannot be submitted to FYERS as an option-premium stop. A future service must monitor NIFTY and submit an option exit when the index threshold is crossed. Realized option loss can differ from the index-distance estimate because of option sensitivity, volatility, spreads, gaps, and exit slippage. The operator does not want a fixed rupee cap per trade and expects an exit when the active index stop is hit. Dashboard stop edits may only tighten the stop; the 1R trigger remains measured from the original entry-to-stop distance. The operator does not want a specific daily loss limit for now; the existing LIVE configuration gate still requires one.

This is a recorded requirement only. It does not enable contract selection, dashboard mutations, a signal worker, or live execution. Hard rupee risk limits have not been supplied. `AppConfig` continues to block LIVE without per-trade and daily risk limits, and the SDK transport is not wired into the application.

The `FyersCompliancePermit` defaults every requirement to false. A missing requirement blocks before the transport is called. Production code does not construct a permit. Enabling the environment toggle alone therefore cannot submit an order. Before wiring the transport, resolve the gates in [fyers_compliance.md](fyers_compliance.md), the unanswered risk limits, NIFTY-only signal validation, option quote and limit-price policy, and the execution/recovery lifecycle.

## Payload contract

- Only LIMIT orders are accepted. NSE's current retail-algo FAQ says algo market orders are prohibited. FYERS' MPP behavior does not make a market-order strategy safe or eligible by inference.
- FYERS product type is explicit. The adapter does not choose delivery/intraday/margin/cover/bracket/MTF terms for a trade.
- Validity is `DAY`; IOC is not implemented.
- Modify requires broker order ID, quantity and limit price. Cancel uses the broker order ID.
- Successful API responses are acknowledgements only; they are not executions/fills.
- SDK/network exceptions and API error message bodies are not propagated, avoiding accidental token/header disclosure.

The order payload fields and modify/cancel shapes follow FYERS-maintained v3 examples and reference material. FYERS sample code and endpoint references differ on the representation of `offlineOrder` (`"False"` in one sample versus a boolean in the endpoint catalog). The transport passes the typed contract's boolean false; this must be confirmed against the active SDK/account before connecting an order workflow.

## Current official constraints reviewed (2026-10-16)

- FYERS says its current API trading setup requires the new app, a registered/mapped static IP and daily 2FA; older apps are data-only. [FYERS app activation](https://support.fyers.in/portal/en/kb/articles/how-do-i-activate-the-new-app-for-api-trading-after-april-1-2026) · [FYERS retail-algo changes](https://support.fyers.in/portal/en/kb/articles/what-are-the-new-sebi-rules-for-retail-algo-trading-from-april-01-2026)
- The NSE implementation standard sets an initial 10 OPS threshold per exchange/segment, requires exchange-provided algo identifiers for audit, static-IP mapping, daily logout and broker risk/security controls. [NSE circular](https://nsearchives.nseindia.com/content/circulars/INVG67858.pdf)
- NSE explains that client API/tech-savvy and vendor-platform hosting paths differ. Its FAQ says algo market orders are prohibited. [NSE retail-algo FAQ](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/FAQ_Retail%20Algo_03112025_NSE.pdf)
- FYERS' official sample shows v3 method names and example payloads for place/modify/cancel. [FYERS v3 sample](https://github.com/FyersDev/fyers-api-sample-code/blob/sample_v3/My%20API%20Sample%20Script%28GET%20STARTED%29/Sample_Test_trading_Data.py) · [FYERS endpoint catalog](https://github.com/FyersDev/fyers-skills/blob/master/skills/fyers-trading/references/endpoints.md)

## Required user/broker confirmations before a real transport

1. Confirm in writing with FYERS which compliance/hosting classification applies to TradingView alerts feeding a user-run Python service, whether any component is treated as a third-party platform, and where the strategy and order-generation logic are permitted to execute.
2. Confirm FYERS app activation, account eligibility, mapped egress IP, daily 2FA/logout/auth flow, API scope and the allowed instrument/product/order types.
3. Confirm the exchange algo registration or registration-free path, exchange algo ID/tagging, required FYERS orderTag mapping, and any strategy-change approval steps.
4. Confirm applicable order rate limits, MPP/limit semantics, broker RMS, and handling of reject/timeout/ambiguous responses.
5. Resolve the strategy-specific option contract selection, lot/risk sizing, stale-alert policy, exit behavior and audited PAPER/shadow test evidence before any deployment gate.

Until those items and the runtime risk gates are complete, do not construct the transport with a satisfied permit or connect it to production signal processing. PAPER remains the default and LIVE remains disabled.
