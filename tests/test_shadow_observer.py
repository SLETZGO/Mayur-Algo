from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from nifty_algo.config import AppConfig
from nifty_algo.dashboard.data import load_snapshot
from nifty_algo.data.database import create_database_engine, create_session_factory
from nifty_algo.data.models import Base, OrderRecord, ShadowObservationRecord
from nifty_algo.services.shadow_observer import (
    PriceReference,
    ShadowEventType,
    ShadowObserver,
    ShadowObservation,
    ShadowRunError,
    ShadowSource,
    ShadowStatus,
)


@pytest.fixture
def observer_db():
    engine = create_database_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


def ts(minute=0):
    return datetime(2026, 10, 16, 4, minute, tzinfo=timezone.utc)


def test_observer_records_shadow_categories_without_creating_orders(observer_db):
    observer = ShadowObserver(observer_db)
    observer.start_run("shadow-1", started_at=ts(), planned_end_at=ts(30))
    records = [
        ShadowObservation(ShadowEventType.SIGNAL_RECEIVED, ShadowSource.TRADINGVIEW, ts(1), event_key="signal-1"),
        ShadowObservation(ShadowEventType.SIGNAL_DUPLICATE, ShadowSource.TRADINGVIEW, ts(2), event_key="signal-1"),
        ShadowObservation(ShadowEventType.SIGNAL_LATE, ShadowSource.TRADINGVIEW, ts(3), source_at=ts(1), event_key="signal-late"),
        ShadowObservation(ShadowEventType.SIGNAL_MISSED, ShadowSource.OPERATOR, ts(4), event_key="signal-missed"),
        ShadowObservation(
            ShadowEventType.QUOTE_RECEIVED, ShadowSource.FYERS, ts(5), symbol="NSE:NIFTY26CE",
            price=Decimal("100"), bid_price=Decimal("99.9"), ask_price=Decimal("100.1"),
            price_reference=PriceReference.BROKER_INSTRUMENT,
        ),
        ShadowObservation(
            ShadowEventType.FEED_GAP, ShadowSource.FYERS, ts(6), metric_value=1500,
            status=ShadowStatus.GAP_DETECTED,
        ),
        ShadowObservation(
            ShadowEventType.PROCESS_RESTART, ShadowSource.SYSTEM, ts(7), event_key="boot-2",
            status=ShadowStatus.PROCESS_STARTED,
        ),
        ShadowObservation(
            ShadowEventType.PROPOSED_CONTRACT, ShadowSource.OPERATOR, ts(8), symbol="NSE:NIFTY26CE",
            price=Decimal("100"), price_reference=PriceReference.BROKER_INSTRUMENT, quantity=25,
        ),
        ShadowObservation(
            ShadowEventType.FILL_ESTIMATE, ShadowSource.OPERATOR, ts(9), symbol="NSE:NIFTY26CE",
            price=Decimal("100.2"), price_reference=PriceReference.BROKER_INSTRUMENT, quantity=25,
            status=ShadowStatus.ESTIMATED,
        ),
        ShadowObservation(
            ShadowEventType.POSITION_MISMATCH, ShadowSource.OPERATOR, ts(10), symbol="NSE:NIFTY26CE",
            quantity=25, comparison_quantity=0,
        ),
    ]
    for record in records:
        observer.record("shadow-1", record)

    summary = observer.summary("shadow-1")
    assert summary.state == "ACTIVE"
    assert summary.planned_end_at == ts(30)
    assert summary.event_counts["SIGNAL_DUPLICATE"] == 1
    assert summary.event_counts["FILL_ESTIMATE"] == 1
    assert summary.event_counts["POSITION_MISMATCH"] == 1
    dashboard = load_snapshot(observer_db, AppConfig())
    assert dashboard.shadow_runs[0].run_id == "shadow-1"
    assert dashboard.shadow_events[0].event_type == "POSITION_MISMATCH"
    with observer_db() as session:
        assert session.scalar(select(func.count()).select_from(ShadowObservationRecord)) == len(records)
        assert session.scalar(select(func.count()).select_from(OrderRecord)) == 0


def test_shadow_run_requires_explicit_valid_window_and_rejects_outside_events(observer_db):
    observer = ShadowObserver(observer_db)
    with pytest.raises(ValueError, match="observation period"):
        observer.start_run("bad", started_at=ts(), planned_end_at=ts())
    with pytest.raises(ValueError, match="timezone-aware"):
        observer.start_run("naive", started_at=datetime(2026, 10, 16), planned_end_at=ts(30))
    observer.start_run("bounded", started_at=ts(), planned_end_at=ts(30))
    with pytest.raises(ShadowRunError, match="outside"):
        observer.record("bounded", ShadowObservation(
            ShadowEventType.SIGNAL_RECEIVED, ShadowSource.TRADINGVIEW, ts(31), event_key="too-late",
        ))


def test_validation_prevents_unit_mixups_and_mislabelled_fill_estimates():
    with pytest.raises(ValueError, match="BROKER_INSTRUMENT"):
        ShadowObservation(
            ShadowEventType.QUOTE_RECEIVED, ShadowSource.FYERS, ts(), symbol="NSE:NIFTY26CE",
            price=Decimal("100"), price_reference=PriceReference.CHART_SYMBOL,
        )
    with pytest.raises(ValueError, match="bid_price"):
        ShadowObservation(
            ShadowEventType.QUOTE_RECEIVED, ShadowSource.FYERS, ts(), symbol="NSE:NIFTY26CE",
            price=Decimal("100"), bid_price=Decimal("101"), ask_price=Decimal("100"),
            price_reference=PriceReference.BROKER_INSTRUMENT,
        )
    with pytest.raises(ValueError, match="positive quantity"):
        ShadowObservation(
            ShadowEventType.PROPOSED_CONTRACT, ShadowSource.OPERATOR, ts(), symbol="NSE:NIFTY26CE",
            price=Decimal("100"), price_reference=PriceReference.BROKER_INSTRUMENT, quantity=0,
        )
    with pytest.raises(ValueError, match="differing observed values"):
        ShadowObservation(
            ShadowEventType.POSITION_MISMATCH, ShadowSource.OPERATOR, ts(), symbol="NSE:NIFTY26CE",
            quantity=25, comparison_quantity=25,
        )


def test_closed_run_rejects_further_observations(observer_db):
    observer = ShadowObserver(observer_db)
    observer.start_run("closed", started_at=ts(), planned_end_at=ts(30))
    observer.close_run("closed", ended_at=ts(20))
    with pytest.raises(ShadowRunError, match="closed"):
        observer.record("closed", ShadowObservation(
            ShadowEventType.SIGNAL_RECEIVED, ShadowSource.TRADINGVIEW, ts(21), event_key="after-close",
        ))
    with pytest.raises(ShadowRunError, match="already closed"):
        observer.close_run("closed", ended_at=ts(22))
