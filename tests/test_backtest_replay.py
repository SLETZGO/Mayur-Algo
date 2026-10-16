from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from nifty_algo.backtest import DataQualityError, ReplayBar, load_bars, replay_signals


def bar(minute, *, up=0, down=0, delta=0, high=101, low=99, session=date(2026, 1, 2)):
    stamp = datetime(2026, 1, 2, 9, 15, tzinfo=timezone(timedelta(hours=5, minutes=30))) + timedelta(minutes=minute)
    return ReplayBar(
        stamp, session, Decimal("100"), Decimal(str(high)), Decimal(str(low)),
        Decimal("100"), Decimal(str(up + down)), Decimal(str(up)), Decimal(str(down)),
        Decimal(str(delta)),
    )


def test_replay_uses_positive_cvd_and_immediate_next_bar_touch():
    bars = (bar(0, up=10, delta=10), bar(5, up=5, delta=5, high=102))
    signals = replay_signals(bars, symbol="NSE:NIFTY50")
    assert len(signals) == 1
    signal = signals[0]
    assert signal.action == "LONG"
    assert signal.entry_trigger == Decimal("101")
    assert signal.stop == Decimal("99")
    assert signal.target == Decimal("107")
    assert signal.cvd_at_setup == Decimal("10")


def test_replay_expires_when_immediate_next_bar_does_not_touch():
    bars = (bar(0, up=10, delta=10), bar(5, up=1, down=1, delta=0, high=100.5), bar(10, high=102))
    assert replay_signals(bars, symbol="NSE:NIFTY50") == ()


def test_replay_uses_negative_cvd_for_short_and_session_date_resets_cvd():
    day_one = (bar(0, up=2, down=1, delta=1),)
    next_session = date(2026, 1, 5)
    next_day_setup = bar(0, down=10, delta=-10, high=101, low=99, session=next_session)
    next_day_touch = ReplayBar(
        next_day_setup.timestamp + timedelta(minutes=5), next_session,
        Decimal("100"), Decimal("101"), Decimal("98"), Decimal("100"),
        Decimal("1"), Decimal("0"), Decimal("1"), Decimal("-1"),
    )
    signals = replay_signals((*day_one, next_day_setup, next_day_touch), symbol="NSE:NIFTY50")
    assert len(signals) == 1
    assert signals[0].action == "SHORT"
    assert signals[0].target == Decimal("93")
    assert signals[0].cvd_at_setup == Decimal("-10")


def test_replay_does_not_treat_gap_bar_as_immediate_confirmation():
    bars = (bar(0, up=10, delta=10), bar(10, high=102))
    assert replay_signals(bars, symbol="NSE:NIFTY50") == ()


def test_replay_refuses_multiple_daily_signals_without_position_simulation():
    with pytest.raises(NotImplementedError, match="position/exit simulation"):
        replay_signals((), symbol="NSE:NIFTY50", one_signal_per_day=False)


def test_csv_loader_requires_timezone_aware_times_and_required_indicator_series(tmp_path):
    csv_path = tmp_path / "bars.csv"
    csv_path.write_text(
        "timestamp,session_date,open,high,low,close,volume,up_volume,down_volume,delta\n"
        "2026-01-02T09:15:00,2026-01-02,100,101,99,100,10,10,0,10\n",
        encoding="utf-8",
    )
    with pytest.raises(DataQualityError, match="UTC offset"):
        load_bars(csv_path)


def test_csv_loader_rejects_missing_five_minute_bars_by_default(tmp_path):
    csv_path = tmp_path / "bars.csv"
    csv_path.write_text(
        "timestamp,session_date,open,high,low,close,volume,up_volume,down_volume,delta\n"
        "2026-01-02T09:15:00+05:30,2026-01-02,100,101,99,100,10,10,0,10\n"
        "2026-01-02T09:25:00+05:30,2026-01-02,100,101,99,100,10,10,0,10\n",
        encoding="utf-8",
    )
    with pytest.raises(DataQualityError, match="missing five-minute"):
        load_bars(csv_path)
