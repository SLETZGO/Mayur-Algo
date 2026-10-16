"""Validated configuration and fail-closed execution-mode controls."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re

from nifty_algo.domain.models import ExecutionMode


class UnsafeConfigurationError(ValueError):
    """Raised when requested execution mode lacks required safeguards."""


@dataclass(frozen=True, slots=True)
class RiskLimits:
    max_risk_per_trade_inr: Decimal | None = None
    max_daily_loss_inr: Decimal | None = None
    max_lots: int = 1
    max_open_positions: int = 1
    max_trades_per_day: int = 1

    def __post_init__(self) -> None:
        for name in ("max_risk_per_trade_inr", "max_daily_loss_inr"):
            value = getattr(self, name)
            if value is not None and (not value.is_finite() or value <= 0):
                raise ValueError(f"{name} must be positive when supplied")
        for name in ("max_lots", "max_open_positions", "max_trades_per_day"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class AppConfig:
    execution_mode: ExecutionMode = ExecutionMode.PAPER
    live_trading_enabled: bool = False
    manual_live_armed: bool = False
    account_configured: bool = False
    compliance_checks_passed: bool = False
    broker_app_activated: bool = False
    static_ip_verified: bool = False
    daily_authentication_complete: bool = False
    database_url: str = "sqlite:///./data/nifty_algo.db"
    webhook_secret: str | None = None
    webhook_max_payload_bytes: int = 8192
    risk_limits: RiskLimits = RiskLimits()

    def __post_init__(self) -> None:
        if self.execution_mode is ExecutionMode.LIVE:
            self.assert_live_ready()
        if not self.database_url.strip():
            raise ValueError("database_url cannot be empty")
        if self.webhook_max_payload_bytes <= 0:
            raise ValueError("webhook_max_payload_bytes must be positive")
        if self.webhook_secret is not None and len(self.webhook_secret.encode("utf-8")) < 32:
            raise ValueError("webhook_secret must contain at least 32 UTF-8 bytes")
        if self.webhook_secret is not None and not re.fullmatch(r"[A-Za-z0-9_-]+", self.webhook_secret):
            raise ValueError("webhook_secret must use URL-safe letters, digits, '-' or '_'")

    def assert_live_ready(self) -> None:
        checks = {
            "live_trading_enabled": self.live_trading_enabled,
            "manual_live_armed": self.manual_live_armed,
            "account_configured": self.account_configured,
            "compliance_checks_passed": self.compliance_checks_passed,
            "broker_app_activated": self.broker_app_activated,
            "static_ip_verified": self.static_ip_verified,
            "daily_authentication_complete": self.daily_authentication_complete,
            "max_risk_per_trade_inr": self.risk_limits.max_risk_per_trade_inr is not None,
            "max_daily_loss_inr": self.risk_limits.max_daily_loss_inr is not None,
        }
        missing = tuple(name for name, passed in checks.items() if not passed)
        if missing:
            raise UnsafeConfigurationError(
                "LIVE mode is blocked; unmet safeguards: " + ", ".join(missing)
            )


def config_from_environment(environ: dict[str, str] | None = None) -> AppConfig:
    """Load only non-secret safety toggles; never load or log credentials here."""
    import os

    source = os.environ if environ is None else environ
    mode_value = source.get("NIFTY_ALGO_EXECUTION_MODE", "PAPER").upper()
    try:
        mode = ExecutionMode(mode_value)
    except ValueError as exc:
        allowed = ", ".join(mode.value for mode in ExecutionMode)
        raise UnsafeConfigurationError(f"invalid execution mode {mode_value!r}; choose {allowed}") from exc

    def enabled(key: str) -> bool:
        value = source.get(key, "false").strip().lower()
        if value not in {"true", "false"}:
            raise UnsafeConfigurationError(f"{key} must be 'true' or 'false'")
        return value == "true"

    # Account/compliance readiness is intentionally not inferred from env toggles.
    # Those proofs must be supplied by a future reviewed compliance service.
    return AppConfig(
        execution_mode=mode,
        live_trading_enabled=enabled("NIFTY_ALGO_LIVE_TRADING_ENABLED"),
        manual_live_armed=enabled("NIFTY_ALGO_MANUAL_LIVE_ARMED"),
        database_url=source.get("NIFTY_ALGO_DATABASE_URL", "sqlite:///./data/nifty_algo.db"),
        webhook_secret=source.get("NIFTY_ALGO_WEBHOOK_SECRET") or None,
        webhook_max_payload_bytes=int(source.get("NIFTY_ALGO_WEBHOOK_MAX_PAYLOAD_BYTES", "8192")),
    )
