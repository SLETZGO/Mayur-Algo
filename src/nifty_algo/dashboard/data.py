"""Read-only dashboard queries; this module never mutates state or calls a broker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from sqlalchemy import desc, select
from sqlalchemy.orm import sessionmaker

from nifty_algo.config import AppConfig
from nifty_algo.data.models import (
    AuditEvent,
    ExecutionRecord,
    OrderRecord,
    PositionRecord,
    ShadowObservationRecord,
    ShadowRunRecord,
    SignalEvent,
)


@dataclass(frozen=True, slots=True)
class SignalRow:
    signal_id: str
    underlying: str
    action: str
    chart_entry_price: str
    chart_stop_price: str
    reward_risk: str
    queue_status: str
    received_at: str
    attempts: int


@dataclass(frozen=True, slots=True)
class OrderRow:
    client_order_id: str
    signal_id: str
    symbol: str
    side: str
    order_type: str
    status: str
    requested_quantity: int
    filled_quantity: int
    limit_price: str | None
    average_fill_price: str | None
    broker_order_id: str | None
    updated_at: str


@dataclass(frozen=True, slots=True)
class ExecutionRow:
    execution_id: str
    client_order_id: str
    symbol: str
    quantity: int
    instrument_price: str
    executed_at: str


@dataclass(frozen=True, slots=True)
class PositionRow:
    symbol: str
    net_quantity: int
    average_instrument_price: str | None
    updated_at: str


@dataclass(frozen=True, slots=True)
class AuditRow:
    event_type: str
    outcome: str
    correlation_id: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ShadowRunRow:
    run_id: str
    state: str
    started_at: str
    planned_end_at: str
    ended_at: str | None


@dataclass(frozen=True, slots=True)
class ShadowEventRow:
    event_type: str
    source: str
    event_key: str | None
    symbol: str | None
    source_at: str | None
    observed_at: str
    price_reference: str
    price: str | None
    bid_price: str | None
    ask_price: str | None
    comparison_price: str | None
    quantity: int | None
    comparison_quantity: int | None
    metric_value: int | None
    status: str | None


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    execution_mode: str
    live_trading_enabled: bool
    manual_live_armed: bool
    database_healthy: bool
    database_error: str | None
    signals: tuple[SignalRow, ...]
    orders: tuple[OrderRow, ...]
    executions: tuple[ExecutionRow, ...]
    positions: tuple[PositionRow, ...]
    audit_events: tuple[AuditRow, ...]
    shadow_runs: tuple[ShadowRunRow, ...] = ()
    shadow_events: tuple[ShadowEventRow, ...] = ()


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def load_snapshot(factory: sessionmaker, config: AppConfig, *, limit: int = 200) -> DashboardSnapshot:
    """Read current durable state. Failures are summarized without leaking DB details."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    try:
        with factory() as session:
            signal_records = session.scalars(
                select(SignalEvent).order_by(desc(SignalEvent.created_at), desc(SignalEvent.id)).limit(limit)
            ).all()
            order_records = session.scalars(
                select(OrderRecord).order_by(desc(OrderRecord.updated_at)).limit(limit)
            ).all()
            execution_records = session.execute(
                select(ExecutionRecord, OrderRecord.symbol)
                .join(OrderRecord, ExecutionRecord.client_order_id == OrderRecord.client_order_id)
                .order_by(desc(ExecutionRecord.executed_at), desc(ExecutionRecord.execution_id))
                .limit(limit)
            ).all()
            position_records = session.scalars(
                select(PositionRecord).order_by(PositionRecord.symbol).limit(limit)
            ).all()
            audit_records = session.scalars(
                select(AuditEvent).order_by(desc(AuditEvent.created_at), desc(AuditEvent.id)).limit(limit)
            ).all()
            shadow_runs = session.scalars(
                select(ShadowRunRecord).order_by(desc(ShadowRunRecord.started_at)).limit(limit)
            ).all()
            shadow_events = session.scalars(
                select(ShadowObservationRecord).order_by(
                    desc(ShadowObservationRecord.observed_at), desc(ShadowObservationRecord.id)
                ).limit(limit)
            ).all()
        return DashboardSnapshot(
            execution_mode=config.execution_mode.value,
            live_trading_enabled=config.live_trading_enabled,
            manual_live_armed=config.manual_live_armed,
            database_healthy=True,
            database_error=None,
            signals=tuple(SignalRow(
                item.signal_id, item.underlying, item.action, item.entry_trigger, item.stop_level,
                item.reward_risk, item.queue_status, _iso(item.created_at), item.processing_attempts,
            ) for item in signal_records),
            orders=tuple(OrderRow(
                item.client_order_id, item.signal_id, item.symbol, item.side, item.order_type,
                item.status, item.requested_quantity, item.filled_quantity, item.limit_price,
                item.average_fill_price, item.broker_order_id, _iso(item.updated_at),
            ) for item in order_records),
            executions=tuple(ExecutionRow(
                item.execution_id, item.client_order_id, symbol, item.quantity, item.price,
                _iso(item.executed_at),
            ) for item, symbol in execution_records),
            positions=tuple(PositionRow(
                item.symbol, item.net_quantity, item.average_price, _iso(item.updated_at),
            ) for item in position_records),
            audit_events=tuple(AuditRow(
                item.event_type, item.outcome, item.correlation_id, _iso(item.created_at),
            ) for item in audit_records),
            shadow_runs=tuple(ShadowRunRow(
                item.run_id, item.state, _iso(item.started_at), _iso(item.planned_end_at), _iso(item.ended_at) or None,
            ) for item in shadow_runs),
            shadow_events=tuple(ShadowEventRow(
                item.event_type, item.source, item.event_key, item.symbol, _iso(item.source_at) or None,
                _iso(item.observed_at), item.price_reference, item.price, item.bid_price, item.ask_price,
                item.comparison_price, item.quantity, item.comparison_quantity, item.metric_value, item.status,
            ) for item in shadow_events),
        )
    except Exception as exc:
        return DashboardSnapshot(
            execution_mode=config.execution_mode.value,
            live_trading_enabled=config.live_trading_enabled,
            manual_live_armed=config.manual_live_armed,
            database_healthy=False,
            database_error=type(exc).__name__,
            signals=(), orders=(), executions=(), positions=(), audit_events=(),
        )
