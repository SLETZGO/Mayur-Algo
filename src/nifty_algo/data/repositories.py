"""Persistence operations for the durable webhook queue."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nifty_algo.data.models import AuditEvent, SignalEvent
from nifty_algo.services.signal_validator import TradingViewAlert


class DuplicateSignalError(Exception):
    pass


def persist_signal(
    session: Session,
    alert: TradingViewAlert,
    correlation_id: str,
    raw_payload_json: str,
) -> SignalEvent:
    record = SignalEvent(
        signal_id=alert.alert_id,
        action=alert.action,
        underlying=alert.underlying,
        entry_trigger=str(alert.entry_trigger),
        stop_level=str(alert.sl_underlying),
        reward_risk=str(alert.rr),
        payload_json=raw_payload_json,
        queue_status="PENDING",
        correlation_id=correlation_id,
    )
    session.add(record)
    session.add(AuditEvent(
        correlation_id=correlation_id,
        event_type="SIGNAL_RECEIVED",
        outcome="ACCEPTED",
    ))
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DuplicateSignalError(alert.alert_id) from exc
    session.refresh(record)
    return record


def record_rejection(session: Session, correlation_id: str, reason: str) -> None:
    session.add(AuditEvent(
        correlation_id=correlation_id,
        event_type="SIGNAL_REJECTED",
        outcome="REJECTED",
        reason=reason[:256],
    ))
    session.commit()


def record_duplicate(session: Session, correlation_id: str) -> None:
    session.add(AuditEvent(
        correlation_id=correlation_id,
        event_type="SIGNAL_DUPLICATE",
        outcome="IGNORED",
    ))
    session.commit()


def claim_next_pending(session: Session) -> SignalEvent | None:
    """Atomically claim one queued event for a future worker; no worker ships yet."""
    event = session.scalar(
        select(SignalEvent)
        .where(SignalEvent.queue_status == "PENDING")
        .order_by(SignalEvent.created_at, SignalEvent.id)
        .limit(1)
    )
    if event is None:
        return None
    claimed = session.execute(
        update(SignalEvent)
        .where(SignalEvent.id == event.id, SignalEvent.queue_status == "PENDING")
        .values(queue_status="PROCESSING", processing_attempts=SignalEvent.processing_attempts + 1)
    )
    if claimed.rowcount != 1:
        session.rollback()
        return None
    session.commit()
    return session.get(SignalEvent, event.id)


def mark_processed(session: Session, signal_id: str) -> None:
    event = session.scalar(select(SignalEvent).where(SignalEvent.signal_id == signal_id))
    if event is None:
        raise LookupError(signal_id)
    if event.queue_status != "PROCESSING":
        raise ValueError("only PROCESSING events can be marked processed")
    event.queue_status = "PROCESSED"
    event.processed_at = datetime.now(timezone.utc)
    session.add(AuditEvent(
        correlation_id=event.correlation_id,
        event_type="SIGNAL_QUEUE_PROCESSED",
        outcome="RECORDED",
    ))
    session.commit()


def release_failed_claim(
    session: Session,
    signal_id: str,
    error: str,
    *,
    max_attempts: int,
) -> str:
    event = session.scalar(select(SignalEvent).where(SignalEvent.signal_id == signal_id))
    if event is None:
        raise LookupError(signal_id)
    if event.queue_status != "PROCESSING":
        raise ValueError("only PROCESSING events can be released")
    event.last_error = error[:256]
    event.queue_status = "FAILED" if event.processing_attempts >= max_attempts else "PENDING"
    session.add(AuditEvent(
        correlation_id=event.correlation_id,
        event_type="SIGNAL_PROCESSING_FAILED",
        outcome=event.queue_status,
        reason="handler_error",
    ))
    session.commit()
    return event.queue_status


def reset_inflight_events(session: Session, *, workers_stopped: bool = False) -> int:
    """Requeue claims only after an operator confirms every consumer is stopped.

    This is intentionally not run automatically by the API: it cannot know whether
    another worker process still owns a claim, and resetting it could duplicate work.
    """
    if not workers_stopped:
        raise ValueError("confirm all workers are stopped before recovering in-flight events")
    events = session.scalars(
        select(SignalEvent).where(SignalEvent.queue_status == "PROCESSING")
    ).all()
    for event in events:
        event.queue_status = "PENDING"
        session.add(AuditEvent(
            correlation_id=event.correlation_id,
            event_type="QUEUE_RECOVERED",
            outcome="REQUEUED",
        ))
    if events:
        session.commit()
    return len(events)


def new_correlation_id() -> str:
    return str(uuid4())
