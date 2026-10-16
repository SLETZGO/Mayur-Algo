# Deployment and live-activation readiness (Stage 10)

**Reviewed:** 2026-10-16. **Current state:** no deployment target or account setup is configured. PAPER remains the default; no live transaction transport exists. This checklist is an engineering control, not legal advice or a broker approval.

## What Stage 10 provides

`nifty_algo.services.deployment_readiness.DeploymentEvidence` produces a fail-closed report from named references to operator-reviewed evidence. Empty evidence blocks both readiness reports. A filled report is not an authorization: it does not contact FYERS, validate a document, change configuration, arm `AppConfig`, deploy a service, or submit orders. Keep evidence documents outside source control and do not place credentials or access tokens in references.

## Deployment gates

Each gate needs a dated, reviewable record and owner before exposing any service:

1. **Broker topology confirmation:** written FYERS/exchange response classifying this exact TradingView alert → Python strategy host → FYERS API arrangement, including whether it is client-generated or vendor/platform hosted and any empanelment requirement.
2. **Approved hosting location:** confirmed permitted host and network topology for the determined classification.
3. **Static egress IP mapping:** stable outbound IP validated from the order-originating host and mapped to the correct activated app/account as FYERS requires.
4. **HTTPS and ingress controls:** valid TLS, restricted ingress, authentication, payload limits, and a reviewed proxy configuration. Never expose the development server directly.
5. **Webhook controls:** public-edge rate limit configured and secret-bearing webhook path redacted from application, proxy, platform, and monitoring logs.
6. **Secrets:** approved secret storage, least privilege, rotation/revocation procedure, and confirmation that secrets do not appear in source, alert bodies, logs, reports, or dashboard output.
7. **Persistence:** production database decision made; backup retention, encryption/access policy, and a successful restore drill recorded. SQLite is local development only.
8. **Operations:** supervised processes, health checks, clock synchronization, actionable monitoring/alerts, disk/database capacity limits, and tested upgrade/rollback procedure.
9. **Incident handling:** reviewed shutdown/kill-switch, broker support/escalation, service recovery and position reconciliation procedures. An emergency manual-position procedure must be broker-confirmed and separately documented.
10. **Shadow evidence:** complete user-defined shadow window, feed coverage, restart/recovery evidence, missed/duplicate/late signal review and manual position comparison. The Stage 9 ledger is currently not connected to signal or quote consumers, so this gate is not met.

## Additional live-activation gates

Live activation is a distinct future change and remains disabled. In addition to all deployment gates, require evidence for:

- FYERS app activation, current permissions and account/app mapping;
- daily authentication and logout procedure tested under the current broker flow;
- exchange algo identifier and broker order-tag behavior confirmed for the exact strategy;
- allowed instruments, products, order types, price protection behavior and contract metadata;
- broker and exchange order-rate limits, broker RMS controls, and client-side throttling tested;
- persistence-backed order/position reconciliation and ambiguous-timeout recovery drill;
- user-approved risk limits and independent compliance review;
- separate, explicit operator approval for live activation after reviewing the concrete change.

No environment variables or readiness references alone may substitute for these approvals. `AppConfig` currently refuses LIVE unless its fail-closed requirements are met, while the environment loader does not infer account or compliance proofs. The mocked FYERS transaction contract has no real transport and is not wired to the order manager. Keep those boundaries intact until the user requests and reviews a later live-enablement change.

## Current official requirements and source limits

The framework and implementation standards apply from 2026-04-01 under SEBI's timeline extension. FYERS' current help guidance says API order placement requires its newly activated app and mapped static IP, daily 2FA, and is subject to a 10 orders/second cap; it also describes market-order conversion to MPP. FYERS says existing apps are data-only after 2026-04-01. NSE's implementation standards and FAQ contain client/API, hosting, tagging, market-order and operational requirements. These generic rules do not determine how this user's exact hybrid topology or account is classified. Verify details directly with FYERS and the relevant exchange at deployment time.

- [SEBI original retail algo circular](https://www.sebi.gov.in/legal/circulars/feb-2025/safer-participation-of-retail-investors-in-algorithmic-trading_91614.html)
- [SEBI implementation timeline extension](https://www.sebi.gov.in/legal/circulars/sep-2025/extension-of-timeline-for-implementation-of-sebi-circular-dated-february-04-2025-on-safer-participation-of-retail-investors-in-algorithmic-trading-_96979.html)
- [NSE implementation standards](https://nsearchives.nseindia.com/content/circulars/INVG67858.pdf)
- [NSE retail algo FAQ](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/FAQ_Retail%20Algo_03112025_NSE.pdf)
- [FYERS retail-algo requirements](https://support.fyers.in/portal/en/kb/articles/what-are-the-new-sebi-rules-for-retail-algo-trading-from-april-01-2026)
- [FYERS new API app activation](https://support.fyers.in/portal/en/kb/articles/how-do-i-activate-the-new-app-for-api-trading-after-april-1-2026)
- [FYERS order restriction troubleshooting](https://support.fyers.in/portal/en/kb/articles/how-to-troubleshoot-api-order-placement-restrictions-sebi-algo-rules)

This documentation is a current engineering summary, not legal advice. It does not establish account eligibility or approval. Recheck primary sources and obtain account-specific written broker confirmation before implementation decisions that depend on compliance.

## Deployment decision

No hosting/provider, domain, production database, static egress IP, account/app approval, secrets manager, or compliance evidence has been supplied. Therefore Stage 10 delivers readiness controls and operational documentation only; deployment and live activation remain pending. PAPER operation stays local and isolated.
