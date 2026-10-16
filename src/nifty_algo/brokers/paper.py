"""Deterministic in-process paper adapter. It has no sockets, credentials, or HTTP client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from nifty_algo.brokers.protocol import (
    AmbiguousBrokerOutcome,
    BrokerAcknowledgement,
    BrokerExecution,
    BrokerOrderSnapshot,
    BrokerPositionSnapshot,
    OrderRequest,
    OrderSide,
)
from nifty_algo.domain.models import ExecutionMode, OrderStatus


@dataclass(slots=True)
class _PaperOrder:
    request: OrderRequest
    snapshot: BrokerOrderSnapshot


class PaperBroker:
    """Manual-fill simulator. Orders never fill unless `emit_execution` is called."""

    mode = ExecutionMode.PAPER

    def __init__(self) -> None:
        self._orders: dict[str, _PaperOrder] = {}
        self._executions: dict[str, BrokerExecution] = {}
        self._positions: dict[str, BrokerPositionSnapshot] = {}
        self.reject_next_submit = False
        self.ambiguous_next_submit = False
        self.ambiguous_next_cancel = False

    def submit(self, request: OrderRequest) -> BrokerAcknowledgement:
        existing = self._orders.get(request.client_order_id)
        if existing is not None:
            if existing.request != request:
                raise ValueError("client_order_id was reused with a different order request")
            snap = existing.snapshot
            return BrokerAcknowledgement(snap.client_order_id, snap.broker_order_id, snap.status)

        broker_id = f"PAPER-{len(self._orders) + 1:08d}"
        status = OrderStatus.REJECTED if self.reject_next_submit else OrderStatus.SUBMITTED
        self.reject_next_submit = False
        snapshot = BrokerOrderSnapshot(
            request.client_order_id, broker_id, status, request.quantity, 0, None,
        )
        self._orders[request.client_order_id] = _PaperOrder(request, snapshot)
        if self.ambiguous_next_submit:
            self.ambiguous_next_submit = False
            raise AmbiguousBrokerOutcome("paper submit acknowledgment was intentionally made ambiguous")
        return BrokerAcknowledgement(request.client_order_id, broker_id, status)

    def cancel(self, client_order_id: str) -> BrokerOrderSnapshot:
        order = self._orders.get(client_order_id)
        if order is None:
            raise AmbiguousBrokerOutcome("paper order is not present in adapter state")
        snap = order.snapshot
        if snap.status in {OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}:
            order.snapshot = BrokerOrderSnapshot(
                snap.client_order_id, snap.broker_order_id, OrderStatus.CANCELLED,
                snap.requested_quantity, snap.filled_quantity, snap.average_fill_price,
            )
        result = order.snapshot
        if self.ambiguous_next_cancel:
            self.ambiguous_next_cancel = False
            raise AmbiguousBrokerOutcome("paper cancel acknowledgment was intentionally made ambiguous")
        return result

    def emit_execution(
        self,
        client_order_id: str,
        *,
        execution_id: str,
        quantity: int,
        price: Decimal,
        executed_at: datetime | None = None,
    ) -> BrokerExecution:
        if execution_id in self._executions:
            existing = self._executions[execution_id]
            candidate = (client_order_id, quantity, price)
            if (existing.client_order_id, existing.quantity, existing.price) != candidate:
                raise ValueError("execution_id was reused with different execution data")
            return existing
        order = self._orders.get(client_order_id)
        if order is None:
            raise LookupError(client_order_id)
        snap = order.snapshot
        if snap.status not in {OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}:
            raise ValueError("only active paper orders can receive executions")
        if quantity <= 0 or snap.filled_quantity + quantity > snap.requested_quantity:
            raise ValueError("execution quantity exceeds order remaining quantity")
        execution = BrokerExecution(
            execution_id, client_order_id, quantity, price,
            executed_at or datetime.now(timezone.utc),
        )
        prior_value = (snap.average_fill_price or Decimal(0)) * snap.filled_quantity
        total_filled = snap.filled_quantity + quantity
        average = (prior_value + price * quantity) / total_filled
        status = OrderStatus.FILLED if total_filled == snap.requested_quantity else OrderStatus.PARTIALLY_FILLED
        order.snapshot = BrokerOrderSnapshot(
            snap.client_order_id, snap.broker_order_id, status,
            snap.requested_quantity, total_filled, average,
        )
        self._executions[execution_id] = execution
        self._apply_position_fill(order.request, quantity, price)
        return execution

    def _apply_position_fill(self, request: OrderRequest, quantity: int, price: Decimal) -> None:
        prior = self._positions.get(request.symbol, BrokerPositionSnapshot(request.symbol, 0, None))
        signed_delta = quantity if request.side is OrderSide.BUY else -quantity
        new_qty = prior.net_quantity + signed_delta
        if prior.net_quantity == 0 or prior.net_quantity * signed_delta > 0:
            old_value = (prior.average_price or Decimal(0)) * abs(prior.net_quantity)
            average = (old_value + price * quantity) / abs(new_qty)
        elif new_qty == 0:
            average = None
        elif prior.net_quantity * new_qty < 0:
            average = price
        else:
            average = prior.average_price
        self._positions[request.symbol] = BrokerPositionSnapshot(request.symbol, new_qty, average)

    def list_orders(self) -> tuple[BrokerOrderSnapshot, ...]:
        return tuple(order.snapshot for order in self._orders.values())

    def list_executions(self) -> tuple[BrokerExecution, ...]:
        return tuple(self._executions.values())

    def list_positions(self) -> tuple[BrokerPositionSnapshot, ...]:
        return tuple(self._positions.values())
