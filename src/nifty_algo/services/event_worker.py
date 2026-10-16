"""Durable queue consumer framework. It cannot call a broker or place orders."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import sessionmaker

from nifty_algo.data.repositories import (
    claim_next_pending,
    mark_processed,
    release_failed_claim,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class QueuedSignal:
    signal_id: str
    action: str
    underlying: str
    payload_json: str
    correlation_id: str
    attempt: int


class SignalHandler(Protocol):
    def __call__(self, signal: QueuedSignal) -> None: ...


class DurableSignalWorker:
    """Claims persisted events and calls an injected idempotent handler.

    No handler is bundled: Stage 2 has no strategy/order behavior. A process that
    crashes after handler success but before acknowledging can deliver again, so
    handlers must be idempotent and own their durable side-effect boundary.
    """

    def __init__(
        self,
        session_factory: sessionmaker,
        handler: SignalHandler,
        *,
        max_attempts: int = 5,
    ) -> None:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        self._session_factory = session_factory
        self._handler = handler
        self._max_attempts = max_attempts

    def run_once(self) -> bool:
        """Process one queued signal; return False when the queue is empty."""
        with self._session_factory() as session:
            record = claim_next_pending(session)
            if record is None:
                return False
            event = QueuedSignal(
                signal_id=record.signal_id,
                action=record.action,
                underlying=record.underlying,
                payload_json=record.payload_json,
                correlation_id=record.correlation_id,
                attempt=record.processing_attempts,
            )

        try:
            self._handler(event)
        except Exception as exc:
            with self._session_factory() as session:
                outcome = release_failed_claim(
                    session,
                    event.signal_id,
                    type(exc).__name__,
                    max_attempts=self._max_attempts,
                )
            logger.error(
                "signal_handler_failed correlation_id=%s signal_id=%s queue_status=%s error_type=%s",
                event.correlation_id,
                event.signal_id,
                outcome,
                type(exc).__name__,
            )
            return True

        with self._session_factory() as session:
            mark_processed(session, event.signal_id)
        logger.info(
            "signal_handler_completed correlation_id=%s signal_id=%s",
            event.correlation_id,
            event.signal_id,
        )
        return True
