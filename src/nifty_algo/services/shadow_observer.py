"""Append-only shadow observation recorder; it has no order/broker dependencies."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from nifty_algo.data.models import ShadowObservationRecord, ShadowRunRecord


class ShadowRunError(RuntimeError):
    pass


class ShadowEventType(StrEnum):
    SIGNAL_RECEIVED = "SIGNAL_RECEIVED"
    SIGNAL_DUPLICATE = "SIGNAL_DUPLICATE"
    SIGNAL_LATE = "SIGNAL_LATE"
    SIGNAL_MISSED = "SIGNAL_MISSED"
    QUOTE_RECEIVED = "QUOTE_RECEIVED"
    FEED_GAP = "FEED_GAP"
    PROCESS_RESTART = "PROCESS_RESTART"
    PROPOSED_CONTRACT = "PROPOSED_CONTRACT"
    FILL_ESTIMATE = "FILL_ESTIMATE"
    POSITION_CHECK = "POSITION_CHECK"
    POSITION_MISMATCH = "POSITION_MISMATCH"


class ShadowSource(StrEnum):
    TRADINGVIEW = "TRADINGVIEW"
    FYERS = "FYERS"
    SYSTEM = "SYSTEM"
    OPERATOR = "OPERATOR"
    PAPER = "PAPER"


class PriceReference(StrEnum):
    NONE = "NONE"
    CHART_SYMBOL = "CHART_SYMBOL"
    BROKER_INSTRUMENT = "BROKER_INSTRUMENT"


class ShadowStatus(StrEnum):
    GAP_DETECTED = "GAP_DETECTED"
    GAP_RECOVERED = "GAP_RECOVERED"
    PROCESS_STARTED = "PROCESS_STARTED"
    MATCHED = "MATCHED"
    MISMATCH = "MISMATCH"
    ESTIMATED = "ESTIMATED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


def _aware(value: datetime | None, field: str, *, required: bool = False) -> None:
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        # SQLite strips timezone metadata for DateTime(timezone=True); all stored values
        # are normalized to UTC before write, so recover that known representation.
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class ShadowObservation:
    event_type: ShadowEventType
    source: ShadowSource
    observed_at: datetime
    source_at: datetime | None = None
    event_key: str | None = None
    symbol: str | None = None
    price_reference: PriceReference = PriceReference.NONE
    price: Decimal | None = None
    bid_price: Decimal | None = None
    ask_price: Decimal | None = None
    comparison_price: Decimal | None = None
    quantity: int | None = None
    comparison_quantity: int | None = None
    metric_value: int | None = None
    status: ShadowStatus | None = None

    def __post_init__(self) -> None:
        _aware(self.observed_at, "observed_at", required=True)
        _aware(self.source_at, "source_at")
        if self.event_key is not None and not self.event_key.strip():
            raise ValueError("event_key cannot be blank")
        if self.symbol is not None and not self.symbol.strip():
            raise ValueError("symbol cannot be blank")
        for name in ("price", "bid_price", "ask_price", "comparison_price"):
            value = getattr(self, name)
            if value is not None and (not value.is_finite() or value <= 0):
                raise ValueError(f"{name} must be finite and positive")
        if self.quantity is not None and self.quantity < 0:
            raise ValueError("quantity cannot be negative")
        if self.comparison_quantity is not None and self.comparison_quantity < 0:
            raise ValueError("comparison_quantity cannot be negative")
        if self.metric_value is not None and self.metric_value < 0:
            raise ValueError("metric_value cannot be negative")
        if self.bid_price is not None and self.ask_price is not None and self.bid_price > self.ask_price:
            raise ValueError("bid_price cannot exceed ask_price")

        if self.event_type in {
            ShadowEventType.SIGNAL_RECEIVED,
            ShadowEventType.SIGNAL_DUPLICATE,
            ShadowEventType.SIGNAL_LATE,
            ShadowEventType.SIGNAL_MISSED,
        } and not self.event_key:
            raise ValueError("signal observations require event_key")
        if self.event_type is ShadowEventType.SIGNAL_LATE and self.source_at is None:
            raise ValueError("late-signal observations require source_at")
        if self.event_type is ShadowEventType.QUOTE_RECEIVED:
            self._require_instrument_price()
        if self.event_type in {ShadowEventType.PROPOSED_CONTRACT, ShadowEventType.FILL_ESTIMATE}:
            self._require_instrument_price()
            if self.quantity is None or self.quantity <= 0:
                raise ValueError("proposed contracts and fill estimates require positive quantity")
        if self.event_type is ShadowEventType.FEED_GAP and self.status is None:
            raise ValueError("feed-gap observations require a typed status")
        if self.event_type is ShadowEventType.FEED_GAP and self.status not in {
            ShadowStatus.GAP_DETECTED, ShadowStatus.GAP_RECOVERED,
        }:
            raise ValueError("feed-gap status must be GAP_DETECTED or GAP_RECOVERED")
        if self.event_type is ShadowEventType.PROCESS_RESTART and self.status is not ShadowStatus.PROCESS_STARTED:
            raise ValueError("process restart must be tagged PROCESS_STARTED")
        if self.event_type is ShadowEventType.FILL_ESTIMATE and self.status is not ShadowStatus.ESTIMATED:
            raise ValueError("fill estimates must be tagged ESTIMATED; they are not executions")
        if self.event_type in {ShadowEventType.POSITION_CHECK, ShadowEventType.POSITION_MISMATCH}:
            if not self.symbol or self.quantity is None or self.comparison_quantity is None:
                raise ValueError("position comparisons require symbol and both quantities")
            differs = self.quantity != self.comparison_quantity or self.price != self.comparison_price
            if self.event_type is ShadowEventType.POSITION_MISMATCH and not differs:
                raise ValueError("position mismatch event requires differing observed values")
            if self.event_type is ShadowEventType.POSITION_CHECK and self.status is None:
                raise ValueError("position checks require a typed status")
            if (self.price is not None or self.comparison_price is not None) and (
                self.price_reference is not PriceReference.BROKER_INSTRUMENT
            ):
                raise ValueError("position prices must be labeled BROKER_INSTRUMENT")

    def _require_instrument_price(self) -> None:
        if not self.symbol or self.price is None:
            raise ValueError("this observation requires symbol and price")
        if self.price_reference is not PriceReference.BROKER_INSTRUMENT:
            raise ValueError("broker quote/contract values must be labeled BROKER_INSTRUMENT")


@dataclass(frozen=True, slots=True)
class ShadowRunSummary:
    run_id: str
    state: str
    started_at: datetime
    planned_end_at: datetime
    ended_at: datetime | None
    event_counts: dict[str, int]


class ShadowObserver:
    """Records explicitly supplied observations; it never creates trade requests."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._factory = session_factory

    def start_run(self, run_id: str, *, started_at: datetime, planned_end_at: datetime) -> None:
        _aware(started_at, "started_at", required=True)
        _aware(planned_end_at, "planned_end_at", required=True)
        if not run_id.strip():
            raise ValueError("run_id is required")
        if planned_end_at <= started_at:
            raise ValueError("planned_end_at must be after started_at; choose the observation period explicitly")
        with self._factory() as session:
            if session.get(ShadowRunRecord, run_id) is not None:
                raise ShadowRunError("shadow run ID already exists")
            session.add(ShadowRunRecord(
                run_id=run_id, state="ACTIVE", started_at=_utc(started_at), planned_end_at=_utc(planned_end_at),
            ))
            session.commit()

    def record(self, run_id: str, observation: ShadowObservation) -> int:
        with self._factory() as session:
            run = session.get(ShadowRunRecord, run_id)
            if run is None:
                raise ShadowRunError("shadow run not found")
            if run.state != "ACTIVE":
                raise ShadowRunError("shadow run is closed")
            observed_at = _utc(observation.observed_at)
            if observed_at < _utc(run.started_at) or observed_at > _utc(run.planned_end_at):
                raise ShadowRunError("observation timestamp is outside the declared run window")
            record = ShadowObservationRecord(
                run_id=run_id,
                event_type=observation.event_type.value,
                source=observation.source.value,
                event_key=observation.event_key,
                symbol=observation.symbol,
                source_at=_utc(observation.source_at),
                observed_at=observed_at,
                price=str(observation.price) if observation.price is not None else None,
                bid_price=str(observation.bid_price) if observation.bid_price is not None else None,
                ask_price=str(observation.ask_price) if observation.ask_price is not None else None,
                comparison_price=str(observation.comparison_price) if observation.comparison_price is not None else None,
                price_reference=observation.price_reference.value,
                quantity=observation.quantity,
                comparison_quantity=observation.comparison_quantity,
                metric_value=observation.metric_value,
                status=observation.status.value if observation.status is not None else None,
            )
            session.add(record)
            session.commit()
            return record.id

    def close_run(self, run_id: str, *, ended_at: datetime) -> None:
        _aware(ended_at, "ended_at", required=True)
        with self._factory() as session:
            run = session.get(ShadowRunRecord, run_id)
            if run is None:
                raise ShadowRunError("shadow run not found")
            if run.state != "ACTIVE":
                raise ShadowRunError("shadow run is already closed")
            ended_at = _utc(ended_at)
            if ended_at < _utc(run.started_at):
                raise ValueError("ended_at cannot precede started_at")
            run.state = "CLOSED"
            run.ended_at = ended_at
            session.commit()

    def summary(self, run_id: str) -> ShadowRunSummary:
        with self._factory() as session:
            run = session.get(ShadowRunRecord, run_id)
            if run is None:
                raise ShadowRunError("shadow run not found")
            rows = session.execute(
                select(ShadowObservationRecord.event_type, func.count(ShadowObservationRecord.id))
                .where(ShadowObservationRecord.run_id == run_id)
                .group_by(ShadowObservationRecord.event_type)
            ).all()
            return ShadowRunSummary(
                run.run_id, run.state, _utc(run.started_at), _utc(run.planned_end_at), _utc(run.ended_at),
                dict(Counter({event_type: count for event_type, count in rows})),
            )
