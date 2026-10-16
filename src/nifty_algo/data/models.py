"""Durable signal-event and queue records."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class SignalEvent(Base):
    __tablename__ = "signal_events"
    __table_args__ = (
        UniqueConstraint("signal_id", name="uq_signal_events_signal_id"),
        Index("ix_signal_events_queue", "queue_status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[str] = mapped_column(String(256), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    underlying: Mapped[str] = mapped_column(String(128), nullable=False)
    entry_trigger: Mapped[str] = mapped_column(String(64), nullable=False)
    stop_level: Mapped[str] = mapped_column(String(64), nullable=False)
    reward_risk: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    queue_status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(256), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class OrderRecord(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("requested_quantity > 0", name="ck_orders_requested_quantity_positive"),
        CheckConstraint("filled_quantity >= 0 AND filled_quantity <= requested_quantity", name="ck_orders_filled_quantity_range"),
        Index("ix_orders_signal_id", "signal_id"),
    )

    client_order_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    signal_id: Mapped[str] = mapped_column(String(256), nullable=False)
    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(8), nullable=False)
    requested_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    limit_price: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    filled_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    average_fill_price: Mapped[str | None] = mapped_column(String(64), nullable=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ExecutionRecord(Base):
    __tablename__ = "executions"

    execution_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    client_order_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("orders.client_order_id"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[str] = mapped_column(String(64), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PositionRecord(Base):
    __tablename__ = "positions"

    symbol: Mapped[str] = mapped_column(String(128), primary_key=True)
    net_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    average_price: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ShadowRunRecord(Base):
    """One explicitly planned shadow observation window; never a trade session."""

    __tablename__ = "shadow_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    planned_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ShadowObservationRecord(Base):
    """Append-only typed shadow evidence; intentionally has no arbitrary JSON payload."""

    __tablename__ = "shadow_observations"
    __table_args__ = (
        Index("ix_shadow_observations_run_time", "run_id", "observed_at"),
        Index("ix_shadow_observations_event_type", "run_id", "event_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("shadow_runs.run_id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    event_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    symbol: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bid_price: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ask_price: Mapped[str | None] = mapped_column(String(64), nullable=True)
    comparison_price: Mapped[str | None] = mapped_column(String(64), nullable=True)
    price_reference: Mapped[str] = mapped_column(String(32), nullable=False, default="NONE")
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comparison_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metric_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(24), nullable=True)
