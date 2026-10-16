from datetime import datetime, timezone

import pytest

from nifty_algo.config import AppConfig
from nifty_algo.dashboard.data import load_snapshot
from nifty_algo.data.database import create_database_engine, create_session_factory
from nifty_algo.data.models import (
    AuditEvent,
    Base,
    ExecutionRecord,
    OrderRecord,
    PositionRecord,
    SignalEvent,
)


@pytest.fixture
def dashboard_db():
    engine = create_database_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    yield factory
    engine.dispose()


def test_snapshot_reads_persisted_signals_orders_fills_positions_and_audit(dashboard_db):
    now = datetime(2026, 10, 16, 4, 0, tzinfo=timezone.utc)
    with dashboard_db() as session:
        session.add(SignalEvent(
            signal_id="signal-1", action="LONG", underlying="NSE:NIFTY50-INDEX",
            entry_trigger="25000", stop_level="24950", reward_risk="3",
            payload_json="{}", queue_status="SUCCEEDED", correlation_id="corr-1",
            created_at=now, processing_attempts=1,
        ))
        session.add(OrderRecord(
            client_order_id="client-1", signal_id="signal-1", symbol="NSE:NIFTY26CE",
            side="BUY", order_type="LIMIT", requested_quantity=25, limit_price="120.5",
            status="FILLED", filled_quantity=25, average_fill_price="120.5",
            broker_order_id="paper-1", correlation_id="corr-1", created_at=now, updated_at=now,
        ))
        session.add(ExecutionRecord(
            execution_id="fill-1", client_order_id="client-1", quantity=25,
            price="120.5", executed_at=now,
        ))
        session.add(PositionRecord(
            symbol="NSE:NIFTY26CE", net_quantity=25, average_price="120.5", updated_at=now,
        ))
        session.add(AuditEvent(
            correlation_id="corr-1", event_type="PAPER_EXECUTION_RECORDED",
            outcome="FILLED", created_at=now,
        ))
        session.commit()

    snapshot = load_snapshot(dashboard_db, AppConfig())
    assert snapshot.database_healthy is True
    assert snapshot.execution_mode == "PAPER"
    assert snapshot.live_trading_enabled is False
    assert snapshot.signals[0].chart_entry_price == "25000"
    assert snapshot.orders[0].average_fill_price == "120.5"
    assert snapshot.executions[0].symbol == "NSE:NIFTY26CE"
    assert snapshot.positions[0].average_instrument_price == "120.5"
    assert snapshot.audit_events[0].event_type == "PAPER_EXECUTION_RECORDED"


def test_snapshot_is_read_only_and_limit_is_enforced(dashboard_db):
    with dashboard_db() as session:
        session.add(SignalEvent(
            signal_id="signal-1", action="LONG", underlying="NSE:NIFTY50-INDEX",
            entry_trigger="25000", stop_level="24950", reward_risk="3",
            payload_json="{}", queue_status="PENDING", correlation_id="corr-1",
        ))
        session.commit()
    before = load_snapshot(dashboard_db, AppConfig())
    after = load_snapshot(dashboard_db, AppConfig())
    assert before == after
    assert len(after.signals) == 1
    with pytest.raises(ValueError, match="limit must be positive"):
        load_snapshot(dashboard_db, AppConfig(), limit=0)


def test_snapshot_reports_database_failure_without_exposing_details():
    engine = create_database_engine("sqlite://")
    factory = create_session_factory(engine)
    engine.dispose()  # The new in-memory connection has no schema, simulating an unavailable DB.
    try:
        snapshot = load_snapshot(factory, AppConfig())
        assert snapshot.database_healthy is False
        assert snapshot.database_error
    finally:
        engine.dispose()
