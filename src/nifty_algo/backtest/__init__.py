"""Deterministic replay of exported Pine indicator inputs (no order simulation)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path


REQUIRED_COLUMNS = {
    "timestamp", "session_date", "open", "high", "low", "close",
    "volume", "up_volume", "down_volume", "delta",
}


class DataQualityError(ValueError):
    """Input data is insufficient or inconsistent for a deterministic replay."""


@dataclass(frozen=True, slots=True)
class ReplayBar:
    timestamp: datetime
    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    up_volume: Decimal
    down_volume: Decimal
    delta: Decimal

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise DataQualityError("bar timestamp must include a UTC offset")
        if self.low <= 0 or self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise DataQualityError("bar has invalid OHLC values")
        if any(value < 0 for value in (self.volume, self.up_volume, self.down_volume)):
            raise DataQualityError("bar volume fields cannot be negative")
        if self.delta != self.up_volume - self.down_volume:
            raise DataQualityError("bar delta must equal up_volume - down_volume")


@dataclass(frozen=True, slots=True)
class ReplaySignal:
    alert_id: str
    action: str
    underlying: str
    setup_time: datetime
    confirmation_time: datetime
    entry_trigger: Decimal
    stop: Decimal
    target: Decimal
    cvd_at_setup: Decimal


def _decimal(raw: str, column: str, row_number: int) -> Decimal:
    try:
        value = Decimal(raw)
    except (InvalidOperation, TypeError):
        raise DataQualityError(f"row {row_number}: {column} is not numeric") from None
    if not value.is_finite():
        raise DataQualityError(f"row {row_number}: {column} must be finite")
    return value


def load_bars(path: str | Path, *, allow_gaps: bool = False) -> tuple[ReplayBar, ...]:
    """Load five-minute data with explicit timestamps and TradingView series.

    `session_date` is deliberately required: Pine's timeframe.change("D")
    boundary is chart/exchange-context dependent and cannot be guessed here.
    """
    bars: list[ReplayBar] = []
    with Path(path).open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        headers = set(reader.fieldnames or ())
        missing = REQUIRED_COLUMNS - headers
        if missing:
            raise DataQualityError(f"missing required CSV columns: {', '.join(sorted(missing))}")
        for row_number, row in enumerate(reader, start=2):
            try:
                timestamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                session = date.fromisoformat(row["session_date"])
            except (ValueError, AttributeError):
                raise DataQualityError(f"row {row_number}: timestamp/session_date is invalid") from None
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise DataQualityError(f"row {row_number}: timestamp must include a UTC offset")
            values = {name: _decimal(row[name], name, row_number) for name in (
                "open", "high", "low", "close", "volume", "up_volume", "down_volume", "delta"
            )}
            if values["low"] <= 0 or values["high"] < max(values["open"], values["close"]):
                raise DataQualityError(f"row {row_number}: invalid OHLC high/low")
            if values["low"] > min(values["open"], values["close"]):
                raise DataQualityError(f"row {row_number}: invalid OHLC low")
            if any(values[key] < 0 for key in ("volume", "up_volume", "down_volume")):
                raise DataQualityError(f"row {row_number}: volume fields cannot be negative")
            if values["delta"] != values["up_volume"] - values["down_volume"]:
                raise DataQualityError(f"row {row_number}: delta must equal up_volume - down_volume")
            bars.append(ReplayBar(timestamp, session, **values))

    if not bars:
        raise DataQualityError("CSV contains no bars")
    for index, (previous, current) in enumerate(zip(bars, bars[1:]), start=3):
        if current.timestamp <= previous.timestamp:
            raise DataQualityError(f"row {index}: timestamps must be strictly increasing")
        if current.session_date == previous.session_date:
            elapsed = current.timestamp - previous.timestamp
            if elapsed < timedelta(minutes=5):
                raise DataQualityError(f"row {index}: duplicate or overlapping five-minute bars")
            if elapsed != timedelta(minutes=5) and not allow_gaps:
                raise DataQualityError(f"row {index}: missing five-minute bar(s); use allow_gaps only after review")
    return tuple(bars)


def replay_signals(
    bars: tuple[ReplayBar, ...],
    *,
    symbol: str,
    one_signal_per_day: bool = True,
    allow_long: bool = True,
    allow_short: bool = True,
) -> tuple[ReplaySignal, ...]:
    """Mirror the supplied Pine setup and immediate-next-bar touch rules.

    A touch is a signal event only. This intentionally does not infer an order
    fill, option contract, option P&L, or same-bar stop/target ordering.
    """
    if not symbol.strip():
        raise ValueError("symbol is required")
    if not one_signal_per_day:
        raise NotImplementedError(
            "one_signal_per_day=False requires position/exit simulation, which is not implemented"
        )
    if not bars:
        return ()
    cvd = Decimal(0)
    session: date | None = None
    used = False
    setup: tuple[ReplayBar, str, Decimal] | None = None
    output: list[ReplaySignal] = []
    for bar in bars:
        if bar.session_date != session:
            session = bar.session_date
            cvd = bar.delta
            used = False
            setup = None
        else:
            cvd += bar.delta

        # A setup can only confirm on the immediately following data bar.
        if setup is not None:
            setup_bar, direction, setup_cvd = setup
            entry = setup_bar.high if direction == "LONG" else setup_bar.low
            is_immediate_next_bar = (
                bar.session_date == setup_bar.session_date
                and bar.timestamp - setup_bar.timestamp == timedelta(minutes=5)
            )
            crossed = is_immediate_next_bar and (
                bar.high >= entry if direction == "LONG" else bar.low <= entry
            )
            if crossed:
                stop = setup_bar.low if direction == "LONG" else setup_bar.high
                risk = abs(entry - stop)
                target = entry + Decimal(3) * risk if direction == "LONG" else entry - Decimal(3) * risk
                utc_time = bar.timestamp.astimezone(timezone.utc)
                epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
                delta_time = utc_time - epoch
                epoch_ms = delta_time.days * 86_400_000 + delta_time.seconds * 1_000 + delta_time.microseconds // 1_000
                alert_id = f"{symbol}-5-{epoch_ms}-{direction}"
                output.append(ReplaySignal(
                    alert_id, direction, symbol, setup_bar.timestamp, bar.timestamp,
                    entry, stop, target, setup_cvd,
                ))
            setup = None

        red = bar.up_volume == 0
        green = not red and bar.down_volume == 0
        highlighted = red or green
        if not highlighted or bar.high <= bar.low or (one_signal_per_day and used):
            continue
        if one_signal_per_day:
            used = True
        if green and cvd > 0 and allow_long:
            setup = (bar, "LONG", cvd)
        elif red and cvd < 0 and allow_short:
            setup = (bar, "SHORT", cvd)
    return tuple(output)
