from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from nifty_algo.brokers.paper import PaperBroker
from nifty_algo.brokers.protocol import OrderRequest, OrderSide, OrderType
from nifty_algo.config import AppConfig
from nifty_algo.data.database import create_database_engine, create_session_factory
from nifty_algo.data.models import AuditEvent, Base, ExecutionRecord, OrderRecord
from nifty_algo.domain.models import ExecutionMode, OrderStatus
from nifty_algo.services.order_manager import IdempotencyConflict, OrderManager, OrderStateError


def setup_manager(broker=None):
    engine = create_database_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    adapter = broker or PaperBroker()
    return factory, adapter, OrderManager(factory, adapter, AppConfig())


def request(client_id="paper-order-1", *, quantity=5, symbol="NSE:NIFTY50", side=OrderSide.BUY):
    return OrderRequest(
        client_order_id=client_id,
        signal_id="signal-1",
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=OrderType.MARKET,
    )


def test_submit_is_idempotent_and_request_conflict_is_rejected():
    factory, broker, manager = setup_manager()
    first = manager.submit(request())
    duplicate = manager.submit(request())
    assert first.status is duplicate.status is OrderStatus.SUBMITTED
    assert first.broker_order_id == duplicate.broker_order_id
    assert len(broker.list_orders()) == 1
    with pytest.raises(IdempotencyConflict):
        manager.submit(request(quantity=4))
    with factory() as session:
        assert len(session.scalars(select(OrderRecord)).all()) == 1


def test_partial_and_complete_executions_update_durable_position():
    factory, broker, manager = setup_manager()
    manager.submit(request())
    first = broker.emit_execution(
        "paper-order-1", execution_id="paper-fill-1", quantity=2,
        price=Decimal("100"), executed_at=datetime(2026, 1, 2, 9, 30, tzinfo=timezone.utc),
    )
    partial = manager.record_execution(first)
    assert partial.status is OrderStatus.PARTIALLY_FILLED
    assert partial.filled_quantity == 2
    second = broker.emit_execution(
        "paper-order-1", execution_id="paper-fill-2", quantity=3,
        price=Decimal("110"), executed_at=datetime(2026, 1, 2, 9, 31, tzinfo=timezone.utc),
    )
    filled = manager.record_execution(second)
    assert filled.status is OrderStatus.FILLED
    assert filled.average_fill_price == Decimal("106")
    position = manager.list_positions()[0]
    assert position.net_quantity == 5
    assert position.average_price == Decimal("106")
    with factory() as session:
        assert len(session.scalars(select(ExecutionRecord)).all()) == 2
        assert session.scalar(select(AuditEvent).where(AuditEvent.event_type == "PAPER_EXECUTION_RECORDED"))


def test_duplicate_execution_delivery_does_not_double_count_position():
    _, broker, manager = setup_manager()
    manager.submit(request())
    execution = broker.emit_execution("paper-order-1", execution_id="same-fill", quantity=2, price=Decimal("100"))
    manager.record_execution(execution)
    manager.record_execution(execution)
    assert manager.get_order("paper-order-1").filled_quantity == 2
    assert manager.list_positions()[0].net_quantity == 2


def test_broker_rejection_is_terminal_and_cannot_be_cancelled():
    _, broker, manager = setup_manager()
    broker.reject_next_submit = True
    rejected = manager.submit(request())
    assert rejected.status is OrderStatus.REJECTED
    assert manager.cancel("paper-order-1").status is OrderStatus.REJECTED


def test_cancel_updates_state_and_stops_later_fills():
    _, broker, manager = setup_manager()
    manager.submit(request())
    assert manager.cancel("paper-order-1").status is OrderStatus.CANCELLED
    with pytest.raises(ValueError, match="active paper orders"):
        broker.emit_execution("paper-order-1", execution_id="late", quantity=1, price=Decimal("100"))


def test_partial_order_can_be_cancelled_after_fill_is_recorded():
    _, broker, manager = setup_manager()
    manager.submit(request())
    execution = broker.emit_execution("paper-order-1", execution_id="partial", quantity=2, price=Decimal("100"))
    manager.record_execution(execution)
    cancelled = manager.cancel("paper-order-1")
    assert cancelled.status is OrderStatus.CANCELLED
    assert cancelled.filled_quantity == 2
    assert manager.list_positions()[0].net_quantity == 2


def test_ambiguous_submit_is_not_retried_and_reconciles_after_restart():
    factory, broker, manager = setup_manager()
    broker.ambiguous_next_submit = True
    first = manager.submit(request())
    assert first.status is OrderStatus.RECONCILIATION_REQUIRED
    duplicate = manager.submit(request())
    assert duplicate.status is OrderStatus.SUBMITTED
    assert len(broker.list_orders()) == 1
    restarted_manager = OrderManager(factory, broker, AppConfig())
    report = restarted_manager.reconcile()
    assert report.reconciled_orders == ("paper-order-1",)
    assert report.unresolved_orders == ()
    assert restarted_manager.get_order("paper-order-1").status is OrderStatus.SUBMITTED


def test_ambiguous_cancel_is_resolved_by_restart_reconciliation():
    factory, broker, manager = setup_manager()
    manager.submit(request())
    broker.ambiguous_next_cancel = True
    assert manager.cancel("paper-order-1").status is OrderStatus.RECONCILIATION_REQUIRED
    restarted_manager = OrderManager(factory, broker, AppConfig())
    assert restarted_manager.reconcile().reconciled_orders == ("paper-order-1",)
    assert restarted_manager.get_order("paper-order-1").status is OrderStatus.CANCELLED


def test_restart_with_missing_adapter_state_fails_closed():
    factory, broker, manager = setup_manager()
    manager.submit(request())
    fresh_adapter = PaperBroker()
    restarted_manager = OrderManager(factory, fresh_adapter, AppConfig())
    report = restarted_manager.reconcile()
    assert report.unresolved_orders == ("paper-order-1",)
    assert restarted_manager.get_order("paper-order-1").status is OrderStatus.RECONCILIATION_REQUIRED


def test_unrecorded_remote_fill_is_not_guessed_during_reconciliation():
    factory, broker, manager = setup_manager()
    manager.submit(request())
    broker.emit_execution("paper-order-1", execution_id="remote-only", quantity=2, price=Decimal("100"))
    report = OrderManager(factory, broker, AppConfig()).reconcile()
    assert report.unresolved_orders == ("paper-order-1",)
    assert report.position_mismatches == ("NSE:NIFTY50",)
    assert manager.get_order("paper-order-1").status is OrderStatus.RECONCILIATION_REQUIRED
    with pytest.raises(OrderStateError, match="blocked until broker"):
        manager.submit(request("paper-order-2"))


def test_untracked_broker_order_blocks_new_order_intents():
    broker = PaperBroker()
    broker.submit(request("orphan-order"))
    _, _, manager = setup_manager(broker)
    with pytest.raises(OrderStateError, match="blocked until broker"):
        manager.submit(request("paper-order-1"))


def test_order_manager_rejects_non_paper_execution_modes():
    with pytest.raises(ValueError, match="only accepts PAPER"):
        OrderManager(None, PaperBroker(), AppConfig(execution_mode=ExecutionMode.SHADOW))


def test_order_manager_rejects_live_marked_adapter_before_any_call():
    class LiveMarkedAdapter:
        mode = ExecutionMode.LIVE
        called = False

        def submit(self, _request):
            self.called = True

    adapter = LiveMarkedAdapter()
    with pytest.raises(ValueError, match="requires a broker adapter marked PAPER"):
        OrderManager(None, adapter, AppConfig())
    assert not adapter.called
