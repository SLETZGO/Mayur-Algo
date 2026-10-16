"""Authenticated, durable TradingView alert intake. This route never places orders."""

from __future__ import annotations

import hmac
import json
import logging
import time
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from nifty_algo.data.repositories import (
    DuplicateSignalError,
    persist_signal,
    record_duplicate,
    record_rejection,
)
from nifty_algo.services.signal_validator import validate_alert

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_session(request: Request):
    factory = request.app.state.session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()


def _correlation_id(request: Request) -> str:
    value = request.headers.get("x-correlation-id", "")
    try:
        return str(UUID(value))
    except (ValueError, AttributeError):
        return str(uuid4())


@router.post("/webhook/tradingview/{webhook_secret}", status_code=status.HTTP_202_ACCEPTED)
async def receive_tradingview_alert(
    webhook_secret: str,
    request: Request,
    response: Response,
    session: Session = Depends(_get_session),
):
    started_at = time.perf_counter()
    configured_secret: str | None = request.app.state.webhook_secret
    correlation_id = _correlation_id(request)
    if not configured_secret or not hmac.compare_digest(webhook_secret, configured_secret):
        logger.warning("webhook authentication rejected correlation_id=%s", correlation_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(status_code=415, detail="Content-Type must be application/json")

    content_length = request.headers.get("content-length")
    max_bytes: int = request.app.state.webhook_max_payload_bytes
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(status_code=413, detail="Payload too large")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid content length") from exc
    body_parts: list[bytes] = []
    body_size = 0
    async for chunk in request.stream():
        body_size += len(chunk)
        if body_size > max_bytes:
            raise HTTPException(status_code=413, detail="Payload too large")
        body_parts.append(chunk)

    try:
        raw_payload_json = b"".join(body_parts).decode("utf-8")
        payload = json.loads(raw_payload_json)
        alert = validate_alert(payload)
    except ValidationError as exc:
        _audit_validation_rejection(session, correlation_id, str(exc))
        raise HTTPException(status_code=422, detail="Invalid signal payload") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        _audit_validation_rejection(session, correlation_id, "invalid_json")
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    try:
        event = persist_signal(session, alert, correlation_id, raw_payload_json)
    except DuplicateSignalError:
        try:
            record_duplicate(session, correlation_id)
        except Exception:
            session.rollback()
            logger.exception("duplicate audit persistence failed correlation_id=%s", correlation_id)
        logger.info("duplicate signal ignored correlation_id=%s", correlation_id)
        return {"status": "duplicate", "signal_id": alert.alert_id, "correlation_id": correlation_id}
    except Exception as exc:
        logger.exception("signal persistence failed correlation_id=%s", correlation_id)
        raise HTTPException(status_code=503, detail="Signal could not be durably stored") from exc

    response.headers["X-Correlation-ID"] = correlation_id
    logger.info(
        "webhook_signal_durably_accepted correlation_id=%s webhook_processing_ms=%.3f",
        correlation_id,
        (time.perf_counter() - started_at) * 1000,
    )
    return {"status": "accepted", "signal_id": event.signal_id, "queue_status": event.queue_status,
            "correlation_id": correlation_id}


def _audit_validation_rejection(session: Session, correlation_id: str, reason: str) -> None:
    try:
        # Never store request body or echo schema error values, which may contain secrets.
        record_rejection(session, correlation_id, "invalid_payload")
    except Exception:
        session.rollback()
        logger.exception("could not persist rejection audit correlation_id=%s", correlation_id)
