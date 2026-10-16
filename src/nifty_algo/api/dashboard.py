"""Read-only API used by the Next.js operations dashboard."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request

from nifty_algo.dashboard.data import load_snapshot

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/snapshot")
def dashboard_snapshot(request: Request) -> dict[str, object]:
    """Return persisted dashboard data and safe configuration metadata only."""
    config = request.app.state.config
    snapshot = load_snapshot(request.app.state.session_factory, config)
    return {
        **asdict(snapshot),
        "settings": {
            "webhook_secret_configured": config.webhook_secret is not None,
            "webhook_max_payload_bytes": config.webhook_max_payload_bytes,
            "risk_limits": {
                "max_risk_per_trade_inr": (
                    str(config.risk_limits.max_risk_per_trade_inr)
                    if config.risk_limits.max_risk_per_trade_inr is not None else None
                ),
                "max_daily_loss_inr": (
                    str(config.risk_limits.max_daily_loss_inr)
                    if config.risk_limits.max_daily_loss_inr is not None else None
                ),
                "max_lots": config.risk_limits.max_lots,
                "max_open_positions": config.risk_limits.max_open_positions,
                "max_trades_per_day": config.risk_limits.max_trades_per_day,
            },
        },
    }
