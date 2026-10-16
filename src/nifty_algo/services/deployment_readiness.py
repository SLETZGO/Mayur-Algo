"""Fail-closed deployment and live-activation readiness reporting.

This module records operator-supplied evidence references; it does not verify
broker/regulatory approval and is not connected to the live execution path.
"""

from __future__ import annotations

from dataclasses import dataclass, field


DEPLOYMENT_GATES: tuple[str, ...] = (
    "broker_topology_confirmation",
    "approved_hosting_location",
    "static_egress_ip_mapping",
    "https_and_ingress_controls",
    "webhook_rate_limit_and_log_redaction",
    "secrets_storage_and_rotation",
    "database_backup_and_restore_drill",
    "process_supervision_and_monitoring",
    "incident_and_emergency_shutdown_runbook",
    "shadow_operation_review",
)

LIVE_GATES: tuple[str, ...] = (
    "activated_fyers_app_and_permissions",
    "same_day_authentication_and_logout_process",
    "exchange_algo_identifier_and_order_tag_mapping",
    "broker_instrument_product_and_order_type_approval",
    "broker_rate_limits_and_rms_confirmed",
    "order_reconciliation_and_recovery_drill",
    "risk_limits_reviewed_and_configured",
    "independent_compliance_review",
    "explicit_operator_live_approval",
)


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    ready: bool
    missing: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DeploymentEvidence:
    """Evidence references keyed by gate; values should identify reviewable records.

    Empty by default. A non-empty string is an assertion/reference only, not
    independent proof that a requirement is satisfied.
    """

    references: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unknown = set(self.references) - set(DEPLOYMENT_GATES) - set(LIVE_GATES)
        if unknown:
            raise ValueError("unknown readiness gate(s): " + ", ".join(sorted(unknown)))
        if any(not isinstance(value, str) or not value.strip() for value in self.references.values()):
            raise ValueError("evidence references must be non-empty strings")

    def report(self, gates: tuple[str, ...]) -> ReadinessReport:
        missing = tuple(gate for gate in gates if not self.references.get(gate, "").strip())
        return ReadinessReport(ready=not missing, missing=missing)

    @property
    def deployment(self) -> ReadinessReport:
        return self.report(DEPLOYMENT_GATES)

    @property
    def live_activation(self) -> ReadinessReport:
        missing = list(self.report(DEPLOYMENT_GATES + LIVE_GATES).missing)
        # Deployment readiness never arms execution; a separate reviewed runtime gate remains.
        return ReadinessReport(ready=not missing, missing=tuple(missing))
