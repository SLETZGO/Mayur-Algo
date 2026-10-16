# Risk Controls

Stage 1 provides `RiskLimits` typed fields and a fail-closed LIVE configuration gate. It does not calculate quantity, evaluate trades, or manage a kill switch. Per-trade and daily loss limits are intentionally `null` until supplied.

Future stages must block entries on stale/ambiguous data, unknown broker state, failed reconciliation, exceeded limits, API/auth or persistence failure, and unresolved contract details. Index levels and option premium values must remain explicitly separated. Existing-position emergency handling must be specified independently from blocking new entries.
