# Stage 4: data validation and deterministic signal replay

Implemented: `load_bars()` validates a CSV with five-minute OHLC, total/up/down volume, delta, timezone-aware timestamps, and explicit `session_date`; it checks ordering, OHLC integrity, volume signs, `delta == up_volume - down_volume`, and missing same-session five-minute bars. `replay_signals()` applies the supplied Pine rules to those series: CVD accumulation/reset by explicit session date, first highlighted bar/day by default, and only immediate-next-bar breakout touch. It emits signal records, not fills.

Replay requires up/down volume and delta exported from the same TradingView indicator/source configuration. It does not recreate TradingView's lower-timeframe library calculation from raw OHLCV. Missing bars fail by default. `allow_gaps=True` is an explicit override for reviewed data only; a gap cannot confirm a pending signal.

No CSV data is present in `data/`, so no actual historical result has been produced. No option contract mapping or expired option time series was supplied. This is not an options backtest, and there are no performance metrics.

## Required CSV columns

`timestamp` (ISO 8601 with UTC offset), `session_date` (ISO `YYYY-MM-DD` following the TradingView chart's daily reset), `open`, `high`, `low`, `close`, `volume`, `up_volume`, `down_volume`, `delta`.

## Unimplemented until requirements/data are supplied

- Fill timing and price; intrabar alert touch versus Pine broker-emulator market order fill at bar close is not resolved.
- Commission, spread, slippage, partial fills, gap handling and same-bar stop/target resolution.
- Option symbol/expiry/strike mapping and historical option bid/ask/trade data. FYERS coverage/plan availability must be verified for the needed contracts and period.
- Session timezone and exact exchange-day reset parity.

Any future report must state dataset provenance, time coverage/granularity, gaps, fill assumptions and costs. Underlying chart points must never be represented as option returns.
