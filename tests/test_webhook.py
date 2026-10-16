import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from nifty_algo.api.app import create_app
from nifty_algo.config import AppConfig
from nifty_algo.data.database import create_database_engine, create_session_factory
from nifty_algo.data.models import AuditEvent, Base, SignalEvent
from nifty_algo.data.repositories import claim_next_pending, reset_inflight_events
from nifty_algo.domain.models import ExecutionMode
from nifty_algo.services.event_worker import DurableSignalWorker


WEBHOOK_SECRET = "test-only-webhook-secret-93e4-test-only-webhook-secret-93e4"
VALID_ALERT = {
    "alert_id": "NSE:NIFTY-5-1792056000000-LONG",
    "action": "LONG",
    "underlying": "NSE:NIFTY50",
    "entry_trigger": 25000.0,
    "sl_underlying": 24950.0,
    "rr": 3.0,
}
VERSIONED_ALERT = {
    **VALID_ALERT,
    "schema_version": 1,
    "strategy_id": "MAYUR_VDBT_RR",
    "strategy_version": "pine-v6-contract-v1",
    "event_type": "ENTRY_SIGNAL",
    "timeframe": "5",
    "reference_instrument": "CHART_SYMBOL",
    "price_unit": "CHART_PRICE",
    "bar_time_epoch_ms": 1792056300000,
    "emitted_at_epoch_ms": 1792056600000,
    "target_price": 25150.0,
}


def make_client(max_payload_bytes=8192):
    engine = create_database_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    app = create_app(
        AppConfig(
            execution_mode=ExecutionMode.PAPER,
            webhook_secret=WEBHOOK_SECRET,
            webhook_max_payload_bytes=max_payload_bytes,
        ),
        session_factory=factory,
    )
    return TestClient(app), factory


def test_valid_signal_is_durably_queued_before_accepted():
    client, factory = make_client()
    raw_payload = json.dumps(VALID_ALERT, indent=2)
    with client:
        response = client.post(
            f"/webhook/tradingview/{WEBHOOK_SECRET}",
            content=raw_payload,
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 202
        assert response.json()["queue_status"] == "PENDING"
        assert response.headers["x-correlation-id"] == response.json()["correlation_id"]
    with factory() as session:
        event = session.scalar(select(SignalEvent))
        assert event is not None
        assert event.signal_id == VALID_ALERT["alert_id"]
        assert event.queue_status == "PENDING"
        assert WEBHOOK_SECRET not in event.payload_json
        assert event.payload_json == raw_payload
        assert session.scalar(select(AuditEvent).where(AuditEvent.event_type == "SIGNAL_RECEIVED"))


def test_duplicate_signal_is_idempotent_and_audited():
    client, factory = make_client()
    with client:
        first = client.post(f"/webhook/tradingview/{WEBHOOK_SECRET}", json=VALID_ALERT)
        duplicate = client.post(f"/webhook/tradingview/{WEBHOOK_SECRET}", json=VALID_ALERT)
    assert first.status_code == 202
    assert duplicate.status_code == 202
    assert duplicate.json()["status"] == "duplicate"
    with factory() as session:
        assert len(session.scalars(select(SignalEvent)).all()) == 1
        assert len(session.scalars(select(AuditEvent).where(AuditEvent.event_type == "SIGNAL_DUPLICATE")).all()) == 1


def test_versioned_pine_alert_is_accepted_and_legacy_contract_remains_supported():
    client, factory = make_client()
    with client:
        response = client.post(f"/webhook/tradingview/{WEBHOOK_SECRET}", json=VERSIONED_ALERT)
    assert response.status_code == 202
    with factory() as session:
        event = session.scalar(select(SignalEvent))
        assert event is not None
        assert event.signal_id == VERSIONED_ALERT["alert_id"]


def test_versioned_alert_requires_full_contract():
    client, factory = make_client()
    incomplete = {**VERSIONED_ALERT, "emitted_at_epoch_ms": None}
    with client:
        response = client.post(f"/webhook/tradingview/{WEBHOOK_SECRET}", json=incomplete)
    assert response.status_code == 422
    with factory() as session:
        assert not session.scalars(select(SignalEvent)).all()


def test_authentication_failure_does_not_persist_or_expose_secret():
    client, factory = make_client()
    with client:
        response = client.post("/webhook/tradingview/wrong-secret", json=VALID_ALERT)
    assert response.status_code == 404
    assert WEBHOOK_SECRET not in response.text
    with factory() as session:
        assert not session.scalars(select(SignalEvent)).all()


def test_invalid_payload_is_rejected_and_audited_without_echoing_body():
    client, factory = make_client()
    bad = {**VALID_ALERT, "action": "BUY", "secret_marker": "do-not-echo"}
    with client:
        response = client.post(f"/webhook/tradingview/{WEBHOOK_SECRET}", json=bad)
    assert response.status_code == 422
    assert "do-not-echo" not in response.text
    with factory() as session:
        assert not session.scalars(select(SignalEvent)).all()
        audit = session.scalar(select(AuditEvent).where(AuditEvent.event_type == "SIGNAL_REJECTED"))
        assert audit is not None and audit.reason == "invalid_payload"


def test_payload_size_limit_is_enforced():
    client, factory = make_client(max_payload_bytes=32)
    with client:
        response = client.post(f"/webhook/tradingview/{WEBHOOK_SECRET}", json=VALID_ALERT)
    assert response.status_code == 413
    with factory() as session:
        assert not session.scalars(select(SignalEvent)).all()


def test_non_json_content_type_is_rejected():
    client, factory = make_client()
    with client:
        response = client.post(
            f"/webhook/tradingview/{WEBHOOK_SECRET}",
            content=json.dumps(VALID_ALERT),
            headers={"content-type": "text/plain"},
        )
    assert response.status_code == 415
    with factory() as session:
        assert not session.scalars(select(SignalEvent)).all()


def test_control_characters_in_log_identifiers_are_rejected():
    client, factory = make_client()
    bad = {**VALID_ALERT, "alert_id": "signal\nforged-log-line"}
    with client:
        response = client.post(f"/webhook/tradingview/{WEBHOOK_SECRET}", json=bad)
    assert response.status_code == 422
    with factory() as session:
        assert not session.scalars(select(SignalEvent)).all()


def test_queue_claim_and_restart_recovery():
    client, factory = make_client()
    with client:
        client.post(f"/webhook/tradingview/{WEBHOOK_SECRET}", json=VALID_ALERT)
    with factory() as session:
        claimed = claim_next_pending(session)
        assert claimed is not None and claimed.queue_status == "PROCESSING"
        assert claimed.processing_attempts == 1
    with factory() as session:
        try:
            reset_inflight_events(session)
        except ValueError as exc:
            assert "confirm all workers are stopped" in str(exc)
        else:
            raise AssertionError("recovery must require explicit worker shutdown confirmation")
        assert reset_inflight_events(session, workers_stopped=True) == 1
        recovered = session.scalar(select(SignalEvent))
        assert recovered is not None and recovered.queue_status == "PENDING"
        assert recovered.processing_attempts == 1
        recovery_audit = session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "QUEUE_RECOVERED")
        )
        assert recovery_audit is not None and recovery_audit.outcome == "REQUEUED"


def test_health_endpoint_reports_without_broker_access():
    client, _ = make_client()
    with client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok", "database": "ready", "execution": "no-order-path"
    }


def test_durable_worker_processes_queue_only_through_injected_handler():
    client, factory = make_client()
    with client:
        client.post(f"/webhook/tradingview/{WEBHOOK_SECRET}", json=VALID_ALERT)
    seen = []
    worker = DurableSignalWorker(factory, seen.append)
    assert worker.run_once() is True
    assert worker.run_once() is False
    assert seen[0].signal_id == VALID_ALERT["alert_id"]
    with factory() as session:
        event = session.scalar(select(SignalEvent))
        assert event is not None and event.queue_status == "PROCESSED"


def test_durable_worker_retries_failure_then_dead_letters():
    client, factory = make_client()
    with client:
        client.post(f"/webhook/tradingview/{WEBHOOK_SECRET}", json=VALID_ALERT)

    def fail_handler(_signal):
        raise RuntimeError("private details must not reach audit records")

    worker = DurableSignalWorker(factory, fail_handler, max_attempts=2)
    assert worker.run_once() is True
    with factory() as session:
        event = session.scalar(select(SignalEvent))
        assert event is not None and event.queue_status == "PENDING"
        assert event.last_error == "RuntimeError"
    assert worker.run_once() is True
    with factory() as session:
        event = session.scalar(select(SignalEvent))
        assert event is not None and event.queue_status == "FAILED"
        assert "private details" not in (event.last_error or "")
