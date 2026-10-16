"""Durable broker-neutral order state machine, gated to the PAPER adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from nifty_algo.brokers.protocol import (
    BrokerExecution,
    BrokerOrderSnapshot,
    BrokerPort,
    OrderRequest,
)
from nifty_algo.config import AppConfig
from nifty_algo.data.models import AuditEvent, ExecutionRecord, OrderRecord, PositionRecord
from nifty_algo.domain.models import ExecutionMode, OrderStatus, PositionStatus


class IdempotencyConflict(ValueError):
    pass


class OrderStateError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ManagedOrder:
    request: OrderRequest
    status: OrderStatus
    filled_quantity: int
    average_fill_price: Decimal | None
    broker_order_id: str | None
    correlation_id: str


@dataclass(frozen=True, slots=True)
class ManagedPosition:
    symbol: str
    status: PositionStatus
    net_quantity: int
    average_price: Decimal | None


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    reconciled_orders: tuple[str, ...]
    unresolved_orders: tuple[str, ...]
    position_mismatches: tuple[str, ...]


class OrderManager:
    """No signal mapping, broker networking, or live execution is performed here."""

    def __init__(self, factory: sessionmaker[Session], broker: BrokerPort, config: AppConfig) -> None:
        self._factory = factory
        self._broker = broker
        self._config = config
        if config.execution_mode is not ExecutionMode.PAPER:
            raise ValueError("Stage 5 order manager only accepts PAPER mode")
        if config.live_trading_enabled:
            raise ValueError("live_trading_enabled must remain false for Stage 5")
        if broker.mode is not ExecutionMode.PAPER:
            raise ValueError("Stage 5 requires a broker adapter marked PAPER")

    def submit(self, request: OrderRequest) -> ManagedOrder:
        report = self.reconcile()
        if report.unresolved_orders or report.position_mismatches:
            raise OrderStateError(
                "new order blocked until broker order and position state is reconciled"
            )
        with self._factory() as session:
            record = session.get(OrderRecord, request.client_order_id)
            if record is not None:
                if not self._same_request(record, request):
                    raise IdempotencyConflict("client_order_id was reused for a different request")
                if record.status == OrderStatus.INTENT.value:
                    self._set_status(session, record, OrderStatus.RECONCILIATION_REQUIRED, "SUBMIT_RECOVERY_REQUIRED")
                return self._view(record)
            record = OrderRecord(
                client_order_id=request.client_order_id,
                signal_id=request.signal_id,
                symbol=request.symbol,
                side=request.side.value,
                order_type=request.order_type.value,
                requested_quantity=request.quantity,
                limit_price=str(request.limit_price) if request.limit_price is not None else None,
                status=OrderStatus.INTENT.value,
                filled_quantity=0,
                average_fill_price=None,
                broker_order_id=None,
                correlation_id=str(uuid4()),
            )
            session.add(record)
            session.add(AuditEvent(
                correlation_id=record.correlation_id,
                event_type="ORDER_INTENT_CREATED",
                outcome="PAPER",
            ))
            session.commit()

        # A crash after INTENT commit is not retried blindly. The stable client ID
        # helps reconciliation, while a duplicate call stays side-effect free.
        try:
            ack = self._broker.submit(request)
        except Exception as exc:
            with self._factory() as session:
                record = self._require(session, request.client_order_id)
                self._set_status(
                    session, record, OrderStatus.RECONCILIATION_REQUIRED,
                    "BROKER_SUBMIT_AMBIGUOUS", type(exc).__name__,
                )
                return self._view(record)
        with self._factory() as session:
            record = self._require(session, request.client_order_id)
            if ack.client_order_id != request.client_order_id or ack.status not in {
                OrderStatus.SUBMITTED, OrderStatus.REJECTED,
            }:
                self._set_status(session, record, OrderStatus.RECONCILIATION_REQUIRED, "INVALID_BROKER_ACK")
            else:
                record.broker_order_id = ack.broker_order_id
                self._set_status(
                    session, record, ack.status,
                    "BROKER_ORDER_ACCEPTED" if ack.status is OrderStatus.SUBMITTED else "BROKER_ORDER_REJECTED",
                    ack.message_code,
                )
            return self._view(record)

    def cancel(self, client_order_id: str) -> ManagedOrder:
        with self._factory() as session:
            record = self._require(session, client_order_id)
            status = OrderStatus(record.status)
            if status in {OrderStatus.CANCELLED, OrderStatus.FILLED, OrderStatus.REJECTED}:
                return self._view(record)
            if status not in {OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}:
                raise OrderStateError(f"cannot cancel order in {status.value} state")
        try:
            snapshot = self._broker.cancel(client_order_id)
        except Exception as exc:
            with self._factory() as session:
                record = self._require(session, client_order_id)
                self._set_status(session, record, OrderStatus.RECONCILIATION_REQUIRED, "BROKER_CANCEL_AMBIGUOUS", type(exc).__name__)
                return self._view(record)
        with self._factory() as session:
            record = self._require(session, client_order_id)
            if snapshot.client_order_id != client_order_id or snapshot.filled_quantity != record.filled_quantity:
                self._set_status(session, record, OrderStatus.RECONCILIATION_REQUIRED, "CANCEL_STATE_MISMATCH")
            else:
                record.broker_order_id = snapshot.broker_order_id
                self._set_status(session, record, snapshot.status, "BROKER_CANCEL_STATE")
            return self._view(record)

    def record_execution(self, execution: BrokerExecution) -> ManagedOrder:
        if execution not in self._broker.list_executions():
            raise OrderStateError("execution was not emitted by the configured adapter")
        with self._factory() as session:
            prior = session.get(ExecutionRecord, execution.execution_id)
            if prior is not None:
                if (prior.client_order_id, prior.quantity, Decimal(prior.price)) != (
                    execution.client_order_id, execution.quantity, execution.price,
                ):
                    raise IdempotencyConflict("execution_id was reused with different execution data")
                return self._view(self._require(session, execution.client_order_id))
            record = self._require(session, execution.client_order_id)
            if record.status not in {OrderStatus.SUBMITTED.value, OrderStatus.PARTIALLY_FILLED.value}:
                raise OrderStateError("only active orders can receive executions")
            prior_filled = sum(session.scalars(select(ExecutionRecord.quantity).where(
                ExecutionRecord.client_order_id == execution.client_order_id
            )).all())
            total_filled = prior_filled + execution.quantity
            if total_filled > record.requested_quantity:
                raise OrderStateError("execution exceeds remaining order quantity")
            snapshot = next((x for x in self._broker.list_orders() if x.client_order_id == execution.client_order_id), None)
            if snapshot is None or snapshot.filled_quantity != total_filled:
                self._set_status(session, record, OrderStatus.RECONCILIATION_REQUIRED, "EXECUTION_TOTAL_MISMATCH")
                return self._view(record)
            session.add(ExecutionRecord(
                execution_id=execution.execution_id,
                client_order_id=execution.client_order_id,
                quantity=execution.quantity,
                price=str(execution.price),
                executed_at=execution.executed_at,
            ))
            fills = session.scalars(select(ExecutionRecord).where(
                ExecutionRecord.client_order_id == execution.client_order_id
            )).all()
            # The new fill is not visible to the SELECT until flush, so include it.
            total_value = sum((Decimal(fill.price) * fill.quantity for fill in fills), Decimal(0))
            total_value += execution.price * execution.quantity
            avg = total_value / total_filled
            record.filled_quantity = total_filled
            record.average_fill_price = str(avg)
            record.broker_order_id = snapshot.broker_order_id
            record.status = snapshot.status.value
            record.updated_at = datetime.now(timezone.utc)
            self._apply_position(session, record.symbol, record.side, execution.quantity, execution.price)
            session.add(AuditEvent(
                correlation_id=record.correlation_id,
                event_type="PAPER_EXECUTION_RECORDED",
                outcome=snapshot.status.value,
            ))
            session.commit()
            return self._view(record)

    def get_order(self, client_order_id: str) -> ManagedOrder:
        with self._factory() as session:
            return self._view(self._require(session, client_order_id))

    def list_positions(self) -> tuple[ManagedPosition, ...]:
        with self._factory() as session:
            records = session.scalars(select(PositionRecord).order_by(PositionRecord.symbol)).all()
            return tuple(ManagedPosition(
                item.symbol,
                PositionStatus.FLAT if item.net_quantity == 0 else PositionStatus.OPEN,
                item.net_quantity,
                Decimal(item.average_price) if item.average_price is not None else None,
            ) for item in records)

    def reconcile(self) -> ReconciliationReport:
        remote_orders = {x.client_order_id: x for x in self._broker.list_orders()}
        remote_execs = {x.execution_id: x for x in self._broker.list_executions()}
        remote_positions = {x.symbol: x for x in self._broker.list_positions()}
        reconciled: list[str] = []
        unresolved: list[str] = []
        mismatches: list[str] = []
        with self._factory() as session:
            records = session.scalars(select(OrderRecord).order_by(OrderRecord.created_at)).all()
            local_execs = session.scalars(select(ExecutionRecord)).all()
            local_by_order: dict[str, list[ExecutionRecord]] = {}
            for execution in local_execs:
                local_by_order.setdefault(execution.client_order_id, []).append(execution)
            for record in records:
                snapshot = remote_orders.get(record.client_order_id)
                local_fills = local_by_order.get(record.client_order_id, [])
                local_ids = {x.execution_id for x in local_fills}
                broker_fills = [x for x in remote_execs.values() if x.client_order_id == record.client_order_id]
                remote_by_id = {x.execution_id: x for x in broker_fills}
                local_by_id = {x.execution_id: x for x in local_fills}
                executions_match = set(remote_by_id) == local_ids and all(
                    (remote_by_id[key].client_order_id, remote_by_id[key].quantity, remote_by_id[key].price,
                     remote_by_id[key].executed_at)
                    == (local_by_id[key].client_order_id, local_by_id[key].quantity, Decimal(local_by_id[key].price),
                        local_by_id[key].executed_at)
                    for key in local_ids
                )
                if snapshot is None or not executions_match:
                    self._set_status(session, record, OrderStatus.RECONCILIATION_REQUIRED, "ORDER_OR_EXECUTION_MISSING")
                    unresolved.append(record.client_order_id)
                    continue
                if (
                    snapshot.requested_quantity != record.requested_quantity
                    or snapshot.filled_quantity != record.filled_quantity
                    or (record.broker_order_id is not None and snapshot.broker_order_id != record.broker_order_id)
                    or snapshot.status not in {
                        OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED,
                        OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED,
                    }
                ):
                    self._set_status(session, record, OrderStatus.RECONCILIATION_REQUIRED, "ORDER_STATE_MISMATCH")
                    unresolved.append(record.client_order_id)
                else:
                    record.broker_order_id = snapshot.broker_order_id
                    record.status = snapshot.status.value
                    record.updated_at = datetime.now(timezone.utc)
                    session.add(AuditEvent(
                        correlation_id=record.correlation_id,
                        event_type="ORDER_RECONCILED",
                        outcome=snapshot.status.value,
                    ))
                    reconciled.append(record.client_order_id)

            local_order_ids = {record.client_order_id for record in records}
            for broker_order_id in sorted(set(remote_orders) - local_order_ids):
                unresolved.append(broker_order_id)
                session.add(AuditEvent(
                    correlation_id=str(uuid4()),
                    event_type="UNTRACKED_BROKER_ORDER",
                    outcome="REVIEW_REQUIRED",
                ))

            local_positions = {x.symbol: x for x in session.scalars(select(PositionRecord)).all()}
            for symbol in sorted(set(local_positions) | set(remote_positions)):
                local = local_positions.get(symbol)
                remote = remote_positions.get(symbol)
                local_qty = local.net_quantity if local else 0
                remote_qty = remote.net_quantity if remote else 0
                local_avg = Decimal(local.average_price) if local and local.average_price else None
                remote_avg = remote.average_price if remote else None
                if local_qty != remote_qty or local_avg != remote_avg:
                    mismatches.append(symbol)
                    session.add(AuditEvent(
                        correlation_id=str(uuid4()),
                        event_type="POSITION_RECONCILIATION_MISMATCH",
                        outcome="REVIEW_REQUIRED",
                        reason="paper_position_snapshot_mismatch",
                    ))
            session.commit()
        return ReconciliationReport(tuple(reconciled), tuple(unresolved), tuple(mismatches))

    @staticmethod
    def _apply_position(session: Session, symbol: str, side: str, quantity: int, price: Decimal) -> None:
        record = session.get(PositionRecord, symbol)
        old_qty = record.net_quantity if record else 0
        old_avg = Decimal(record.average_price) if record and record.average_price else None
        signed_delta = quantity if side == "BUY" else -quantity
        new_qty = old_qty + signed_delta
        if old_qty == 0 or old_qty * signed_delta > 0:
            old_value = (old_avg or Decimal(0)) * abs(old_qty)
            new_avg = (old_value + price * quantity) / abs(new_qty)
        elif new_qty == 0:
            new_avg = None
        elif old_qty * new_qty < 0:
            new_avg = price
        else:
            new_avg = old_avg
        if record is None:
            record = PositionRecord(symbol=symbol, net_quantity=new_qty, average_price=str(new_avg) if new_avg else None)
            session.add(record)
        else:
            record.net_quantity = new_qty
            record.average_price = str(new_avg) if new_avg is not None else None
            record.updated_at = datetime.now(timezone.utc)

    @staticmethod
    def _same_request(record: OrderRecord, request: OrderRequest) -> bool:
        return (
            record.signal_id == request.signal_id and record.symbol == request.symbol
            and record.side == request.side.value and record.order_type == request.order_type.value
            and record.requested_quantity == request.quantity
            and (Decimal(record.limit_price) if record.limit_price else None) == request.limit_price
        )

    @staticmethod
    def _view(record: OrderRecord) -> ManagedOrder:
        from nifty_algo.brokers.protocol import OrderSide, OrderType
        return ManagedOrder(
            OrderRequest(
                record.client_order_id, record.signal_id, record.symbol,
                OrderSide(record.side), record.requested_quantity, OrderType(record.order_type),
                Decimal(record.limit_price) if record.limit_price is not None else None,
            ),
            OrderStatus(record.status), record.filled_quantity,
            Decimal(record.average_fill_price) if record.average_fill_price is not None else None,
            record.broker_order_id, record.correlation_id,
        )

    @staticmethod
    def _require(session: Session, client_order_id: str) -> OrderRecord:
        record = session.get(OrderRecord, client_order_id)
        if record is None:
            raise LookupError(client_order_id)
        return record

    @staticmethod
    def _set_status(
        session: Session,
        record: OrderRecord,
        status: OrderStatus,
        event_type: str,
        reason: str | None = None,
    ) -> None:
        record.status = status.value
        record.updated_at = datetime.now(timezone.utc)
        session.add(AuditEvent(
            correlation_id=record.correlation_id,
            event_type=event_type,
            outcome=status.value,
            reason=reason[:256] if reason else None,
        ))
        session.commit()
