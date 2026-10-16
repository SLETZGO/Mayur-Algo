# Shadow Operation Readiness (Stage 9)

## What is implemented

`services/shadow_observer.py` records a user-defined, bounded shadow window and typed observations in append-only `shadow_runs` / `shadow_observations` tables. It supports signal receipt/duplicate/late/missed markers, quotes, feed-gap markers, process restart markers, proposed contracts, fill estimates, and position checks/mismatches. All timestamps are timezone-aware at the service boundary and normalized to UTC for persistence.

Observation records use explicit columns instead of arbitrary JSON; there is no credential or raw webhook-body field. Callers should pass only stable event identifiers, never secrets. Prices carry `CHART_SYMBOL`, `BROKER_INSTRUMENT`, or `NONE` references. Contract and quote observations require broker-instrument units. A `FILL_ESTIMATE` must be tagged `ESTIMATED`; it cannot be confused with an actual `ExecutionRecord`. Recording any observation never routes to `OrderManager` or a broker.

The dashboard has a Shadow Runs view for the persisted run and observation tape. It does not control runs or initiate feed connections.

## Operation has not started

No shadow run was created during implementation. There is no FYERS quote WebSocket connection, no connected account, no webhook secret or public HTTPS receiver configured, no TradingView alert delivery evidence, and no observation period defined. The observer is instrumentation only; it is not yet wired to the TradingView receiver, FYERS stream, or order/position reconciler. No real signals/quotes, candidate contracts, estimated fills, or manual position comparisons have been recorded.

Stage 6's FYERS adapter is read-only REST and disabled by default; its live data socket was not implemented. The stage 7 transaction layer remains a mock contract. Orders remain disabled.

## Inputs needed before starting a measured run

1. User-defined observation start/end times and timezone.
2. Chosen signal delivery setup and local webhook secret (keep it out of chat); for TradingView cloud alerts, a reachable HTTPS endpoint and access-log redaction are required.
3. FYERS account/app read permission and a valid token configured locally if broker quotes/positions are to be included. No token needs to be sent here.
4. A defined stale-alert threshold and clock-skew policy, since current ingestion accepts legacy alerts and does not classify them as late.
5. Explicit option contract selection, lot sizing, and the source/assumptions for any proposed-fill estimate. The observer records values supplied to it and does not select contracts or invent fills.
6. A process for manual broker-vs-local position checks and escalation of mismatches.

After these are supplied, wire signal intake, read-only market data, restart reporting and manual comparison into the observer, run the chosen period in SHADOW mode, then review duplicate/missed/late events, gaps, restarts, contract proposals, fill estimates and mismatches. The observation period is user-selected; no duration or performance threshold is assumed here.
