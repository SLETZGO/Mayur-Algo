# Stage 0 Repository Audit

**Checked:** 2026-10-15 (Asia/Kolkata)  
**Scope:** Initial inventory and official documentation review. Stage 1 implementation and verification are recorded in `CODEX_BUILD_PLAN.md`.

## Workspace inventory

The configured project directory `S:\Mayur Algo` is empty. No tracked repository or `.git` metadata is present, so there is no branch or working-tree status to report. No project subdirectories or files were found.

| Requested artifact | Finding |
|---|---|
| Pine Script | User subsequently supplied a complete Pine v6 script as an attachment on 2026-10-15. It is read and transcribed in `docs/strategy_spec.md`, but remains outside the project tree. |
| Python source | None found; no working application behavior can be preserved or assessed. |
| CSV / historical data | None found; no data shape, coverage, provenance, or quality can be assessed. |
| Configuration / tests / dependency manifests | None found. |
| Git repository | None found at the configured path. |
| Master specification | Read from the supplied Downloads path; it is a design/build specification and explicitly says it does not imply functioning software or live authorization. |

The master specification is treated as project guidance. The provided Pine attachment is now the source for documented signal behavior; it does not define option contract selection or grant account-specific broker approval. No additional strategy logic has been invented.

## Existing behavior and preservation

There is no existing project code or data in this workspace to explain or preserve. Stage 0 has created only documentation files. The user-supplied master specification and Pine attachment remain outside the project workspace and were not modified. The user clarified that the empty structure is intentional and the project is to be created according to the build plan.

The Pine source defines a 5-minute chart strategy based on up/down volume classification and daily CVD; its rules, inputs, chart-price levels, 3R exit and alert payload are documented in `docs/strategy_spec.md`. It does not implement option selection or order execution through FYERS.

## Official sources reviewed

The source links and findings below were checked on 2026-10-15. Regulatory information is a technical project gate, not individualized legal advice. Confirm the exact deployment and account treatment with FYERS/compliance before any transaction integration.

### TradingView webhooks

- [TradingView: How to configure webhook alerts](https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/): webhook alerts issue HTTP POST; valid JSON is sent as `application/json`; webhook destinations with explicit ports are limited to 80 and 443; requests taking over three seconds are cancelled; IPv6 is unsupported; TradingView publishes sender IPs for allowlisting; webhook delivery can fail and status is visible in the alert log; account 2FA is required. This supports a quick-acknowledgement, durable-persist-before-ack design, but does not guarantee delivery.

### FYERS API and retail-algo guidance

- [FYERS API portal](https://myapi.fyers.in/): official API entry point and documentation portal. Exact v3 request/response schemas must be rechecked against its current endpoint docs before implementation; no endpoint schema was inferred in Stage 0.
- [FYERS: Retail algo rules from 1 April 2026](https://support.fyers.in/portal/en/kb/articles/what-are-the-new-sebi-rules-for-retail-algo-trading-from-april-01-2026): FYERS describes validated whitelisted static IP mapped to the API app, daily 2FA, maximum 10 orders/second, market orders converted to MPP-protected orders, and third-party platforms needing empanelment and broker-infrastructure hosting.
- [FYERS: New API app activation after 1 April 2026](https://support.fyers.in/portal/en/kb/articles/how-do-i-activate-the-new-app-for-api-trading-after-april-1-2026): legacy apps become data-only; a newly activated app, static-IP mapping, redirect URL and selected permissions are required for API order placement. FYERS describes the new app ID type as ending in 200.
- [FYERS: Order-placement restriction troubleshooting](https://support.fyers.in/portal/en/kb/articles/how-to-troubleshoot-api-order-placement-restrictions-sebi-algo-rules): corroborates the new app, matching whitelisted outbound IP and app type 200 checks.
- [FYERS: Market Price Protection](https://support.fyers.in/portal/en/kb/articles/what-is-market-price-protection-mpp-in-fyers): FYERS says market orders are converted into protected limit orders; orders may remain pending if market price moves beyond the band. Any future execution model must account for pending/non-fill behavior.
- [FYERS: API Standard/Prime rate limits and data access](https://support.fyers.in/portal/en/kb/articles/what-are-the-fyers-api-rate-limits-for-standard-and-prime-plans): current published page describes category-specific plan limits. It lists expired F&O intraday as 10 requests/day on Standard and available within Prime limits; published historical/seconds coverage and request limits differ by plan. Account entitlements and exact endpoint constraints remain unverified.
- [FYERS: User-app authentication flow](https://support.fyers.in/portal/en/kb/articles/how-does-the-authentication-and-login-flow-work-for-user-apps-on-fyers): describes user redirection, auth code, app ID hash and access token flow. Do not automate or bypass user 2FA; verify the mandated daily flow for the specific activated app.

### Indian retail-algo framework

- [SEBI circular, 4 February 2025](https://www.sebi.gov.in/legal/circulars/feb-2025/safer-participation-of-retail-investors-in-algorithmic-trading_91614.html): primary framework source for safer retail participation in algorithmic trading.
- [NSE implementation standards PDF](https://nsearchives.nseindia.com/content/circulars/INVG67858.pdf): includes client static-IP mapping requirements for API access.
- [NSE retail-algo FAQ PDF](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/FAQ_Retail%20Algo_03112025_NSE.pdf): distinguishes a tech-savvy investor using their own API from vendor-provided algos and states broker-server hosting for provider algos. This makes classification and hosting of this proposed TradingView webhook → Python → FYERS architecture material and unresolved.
- [NSE operational modalities update](https://nsearchives.nseindia.com/content/circulars/INSP73850.pdf): current exchange implementation material includes API static-IP controls and broker-cloud hosting distinctions/exceptions.
- [SEBI September 2025 implementation timeline circular](https://www.sebi.gov.in/sebi_data/attachdocs/sep-2025/1759232056254.pdf): states the 1 April 2026 applicability date for the framework and exchange implementation modalities for stock brokers.

## Compliance assessment and live gate

The intended system receives TradingView webhooks and would originate orders through FYERS API. A self-developed personal strategy may be treated differently from an algo-provider/third-party platform arrangement, but the public sources reviewed do not establish that this exact topology and hosting arrangement is permitted for this user's account. In particular, FYERS's general statement about third-party platforms requiring empanelment and broker hosting must be reconciled with the exchange's tech-savvy-client provisions by FYERS for this exact topology.

Therefore the project is not cleared for live order placement. Future transaction code must remain disabled unless and until all required checks are verified, recorded and explicitly approved. Stage 0 has not contacted FYERS or accessed the user's account.

## Missing information needed to reproduce the indicator

1. Actual TradingView chart symbol/session and Python timezone/session parity.
2. Whether alert/replay semantics are intrabar touch or only confirmed close; source has `calc_on_every_tick=true` and breakout tests without `barstate.isconfirmed`, while expiration is close-confirmed.
3. Intended long/short-to-option mapping, expiry/strike selection, risk budget, quantity and explicit loss limits.
4. Whether exits are monitored on underlying levels or a separate option-premium formula. The source's stop and 3R target are chart-price levels.
5. Gap-through, partial fill, rejected/non-fill, simultaneous stop/target and emergency-exit policies.
6. Historical input files/provenance and desired repository path for the attached Pine source.
7. User/FYERS confirmation of account eligibility, app type/permissions, static-IP mapping, rate/MPP behavior, daily auth, data plan/expired options coverage, and whether this exact webhook/server architecture is allowed and where it must run.

No credentials, access tokens, 2FA codes, or other secrets are needed for Stage 0 and none were requested.

## Stage 0 change and verification record

Created `REPOSITORY_AUDIT.md`, `docs/architecture.md`, `docs/strategy_spec.md`, and `CODEX_BUILD_PLAN.md`. At Stage 0, the Pine attachment was read completely and transcribed into the strategy spec; no application code, dependencies, data, or tests were added because Stage 0 is documentation discovery.

## Follow-up after Stages 1–4

The source is now tracked byte-for-byte at `pine/mayur_vdbt_rr_original.pine`; the alert-only v1 copy is `pine/mayur_vdbt_rr_v1.pine`. Stages 1–3 and the Stage 4 CSV validator/signal-only replay are implemented. Stage 5 adds a network-free PAPER adapter and durable order/position manager; there is still no FYERS integration. The current `data/` directory remains empty; therefore there are no observed datasets, historical results, or option P&L. FYERS historical/expired F&O API-plan coverage and current retail-algo order requirements were rechecked on 2026-10-16 and are summarized with official links in `docs/fyers_compliance.md`. No credentials were requested, and live trading remains disabled.
