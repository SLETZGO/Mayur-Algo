# Strategy Specification — MAYUR VDBT RR

**Source:** user-pasted Pine Script v6. The exact supplied source is preserved in `pine/mayur_vdbt_rr_original.pine` (SHA-256 `077208BFA247442BB7BB24E0B036228EA5F05E0B8FB56C417E20B6F8BFAC7679`). `pine/mayur_vdbt_rr_v1.pine` is the alert-contract integration copy; strategy conditions/order calls are unchanged, and only the alert JSON construction was changed. Pine runtime parity is not yet proven.

## Strategy and chart requirements

- Pine strategy title: `MAYUR's Vol/Delta + CVD Progressive RR`; short title `MAYUR VDBT RR`.
- Requires a five-minute chart; the script raises a runtime error otherwise.
- Runs on the chart's symbol (`syminfo.tickerid`). The webhook currently accepts NIFTY index symbols only; SENSEX is deferred. No actual ticker is hardcoded. It requires vendor volume data and raises an error if cumulative volume is zero.
- TradingView strategy settings: `pyramiding=0`, initial capital 100,000, fixed quantity 1, commission 0.05 percent, slippage 1 tick, `process_orders_on_close=true`, `calc_on_every_tick=true`.
- Imports `TradingView/ta/8` and calls `ta.requestUpAndDownVolume(lowerTF)`. The default lower timeframe is one minute on intraday charts; an input can select a custom timeframe (custom value defaults to `1`, but custom mode defaults off).

## Candle classification and daily CVD

- `isRed` means `upVolume == 0`.
- `isGreen` means not red and `downVolume == 0`.
- Highlighted candles are either class; candles with neither condition are not highlighted. Candles with `high <= low` are excluded from entries.
- CVD resets when `timeframe.change("D")` is true, initializing from current delta (with `nz`); otherwise it accumulates delta with `nz`.
- Long eligibility requires CVD strictly positive; short eligibility requires CVD strictly negative. CVD exactly zero permits neither direction.
- Daily boundary/session interpretation depends on chart/symbol context; the target Python timezone/session convention must be confirmed against expected examples.

## Signal limiting and setup

- Inputs default to `oneSignalPerDay=true`, `allowLong=true`, `allowShort=true`.
- `firstHighlight` requires five-minute chart, confirmed bar, green or red classification, `high > low`, flat Pine position, no pending order, no active signal bar, and (unless disabled) no prior highlighted candle consumed that day.
- On any `firstHighlight`, `signalUsedToday` is set when one-signal-per-day is enabled, even if CVD/direction filters prevent a trade. Thus the first highlighted candle can consume the day's opportunity without creating a setup.
- Long setup: eligible green candle with positive CVD and longs enabled. Trigger is that signal candle's high; stop is its low; risk is high minus low; final target is trigger plus 3 times risk.
- Short setup: eligible red candle with negative CVD and shorts enabled. Trigger is that signal candle's low; stop is its high; risk is high minus low; final target is trigger minus 3 times risk.
- No order is submitted on the highlighted setup candle. The immediately following five-minute candle is the only confirmation candle.
- Long confirms if that next bar's high is at/above trigger; short confirms if its low is at/below trigger. If that immediate next bar closes without crossing, setup expires. Later bars cannot trigger it. Expiration does not reset `signalUsedToday`, so no second attempt is allowed that day when one-signal-per-day is enabled.
- Pine `strategy.entry` and bracket `strategy.exit` are submitted on breakout. Exit bracket uses the setup candle's stop and 3R target. There is no trailing stop.
- Pine position direction is long/short in the chart instrument. The script does not select or trade options itself.

## Alerts and units

The script calls `alert()` on next-bar breakout, with `alert.freq_once_per_bar`. The original payload's six fields remain accepted. The v1 payload adds `schema_version=1`, `strategy_id=MAYUR_VDBT_RR`, `strategy_version=pine-v6-contract-v1`, `event_type=ENTRY_SIGNAL`, `timeframe=5`, `reference_instrument=CHART_SYMBOL`, `price_unit=CHART_PRICE`, `bar_time_epoch_ms`, `emitted_at_epoch_ms`, and `target_price`. `bar_time_epoch_ms` is the breakout bar's opening time; `emitted_at_epoch_ms` is `timenow`, both UNIX milliseconds. The stable `alert_id` remains `<tickerid>-5-<breakout-bar-time>-LONG|SHORT`. Numeric levels are formatted to `format.mintick`; `rr` is 3.0.

`underlying` and all levels remain chart symbol prices (called `CHART_PRICE` in v1), not option-premium prices. The receiver authenticates separately and never receives a webhook secret in the body. The receiver captures v1 timestamps but does not reject stale events until a maximum-age/clock policy is specified. Existing TradingView alerts are snapshots; create/recreate the alert using the updated script before expecting the v1 body.

## Exit and display behavior

- Final Pine exit is stop or 3R limit. Displayed 1R, 1.5R, 2R and 3R levels are informational; only stop and 3R are submitted in the exit bracket.
- Dashboard tracks today's setup values and progressive reward status. It resets on `newDay`.
- Pine simulation uses percentage commission, one-tick slippage, fixed size 1 and chart-level price P&L. These do not represent option trading P&L or all-in brokerage/taxes.
- Same-bar stop/target resolution depends on TradingView broker-emulator settings/data granularity. Python replay must not assume favorable ordering; establish conservative policy and fixture comparison.

## Timing ambiguity before parity implementation

Next-bar breakout booleans do not include `barstate.isconfirmed`, and `calc_on_every_tick=true`; `alert.freq_once_per_bar` can therefore emit on an intrabar touch. A separate expiration block expires only at bar confirmation, while comments describe confirmation and expiry by candle close. Historical OHLC cannot determine precise intrabar event/order or reproduce realtime alert timing. Confirm whether replay should model first-touch intrabar or only a confirmed next-bar close, and whether alerts are intended on trigger or confirmed close.

## NIFTY options application requirements

1. TradingView chart/session settings for the NIFTY index.
2. Whether long means buy CE and short means buy PE; whether short instead means short the underlying/option.
3. Expiry, strike/offset, quote freshness/liquidity, quantity, maximum risk per trade and maximum daily loss.
4. Whether stop/3R target are monitored on underlying levels or an independently specified option-premium formula. No index-to-premium conversion is defined.
5. Gap-through trigger/stop handling, partial fills, rejected/non-filled orders, simultaneous stop/target touches, session reset/timezone.
6. Historical underlying and option datasets, provenance, granularity and coverage for parity and option-level backtests.
7. Verify Pine compilation and v1 output in TradingView, then recreate the alert using the versioned script.

No credentials are needed for these clarifications. Execution remains PAPER by default and live orders remain disabled.

## Current scope and target requirements

- Current scope is TradingView NIFTY index signals and NIFTY ATM options via FYERS. SENSEX support is deferred.
- Bullish-to-CE and bearish-to-PE is presented as a default mapping in the design document, not evidence of the user's current strategy intent.
- Levels produced on a NIFTY index chart must not be treated as option-premium prices.
- The exit model, contract selection, entry timing, exits, trailing, risk budget, quantity, session behavior and re-entry remain unconfirmed.
- Execution must default to PAPER and live orders must remain disabled until compatibility and compliance checks are complete.

## Information required for faithful reproduction

The source and chart/timeframe are now supplied; remaining data and application decisions are:

1. Actual chart symbol/session and intended Python timezone/session semantics.
2. Intrabar-touch versus confirmed-close alert/replay semantics described above.
3. Option mapping, expiry/strike, sizing/risk, quote/liquidity and exit model.
4. Gap-through, partial/rejected order, same-bar exit and force-exit behavior.
5. Historical files and provenance, timestamps/timezone, bar size, contract mapping and gaps.
6. Verify Pine compilation and v1 alert output in TradingView, and select the chart/session convention.

## Rules intentionally not inferred

No ATM selection, nearest expiry, premium stop, risk amount, trailing behavior, market order type, or live deployment permission is inferred. Five-minute timeframe and one-signal-per-day are actual Pine defaults, with corresponding user inputs.

## Verification status

The original script is preserved byte-for-byte; the integration copy changes alert payload construction only. A strict v1 alert schema and legacy v0 compatibility are implemented. Stage 4 has a CSV validator and deterministic signal-only replay over TradingView-exported OHLC/up-volume/down-volume/delta data. Unit tests cover long setup/touch, immediate-bar expiry, missing bars, and versioned payload validation. No user data exists yet, and Pine Editor/runtime parity or any performance backtest has not been verified.
