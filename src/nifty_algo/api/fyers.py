"""Explicit FYERS read-only connection check for the local dashboard."""

from __future__ import annotations

from fastapi import APIRouter

from nifty_algo.brokers.fyers_readonly import (
    FyersAPIError,
    FyersReadOnlyClient,
    FyersReadOnlyDisabled,
    FyersReadOnlyError,
)

router = APIRouter(prefix="/fyers", tags=["fyers-read-only"])


@router.post("/connect")
def connect_read_only() -> dict[str, str | bool]:
    """Validate the local FYERS session with one profile read; disclose no profile data."""
    try:
        client = FyersReadOnlyClient.from_environment()
        client.get_profile()
    except FyersReadOnlyDisabled:
        return {
            "connected": False,
            "mode": "DISABLED",
            "message": "FYERS read-only access is disabled in the local environment.",
        }
    except FyersAPIError:
        return {
            "connected": False,
            "mode": "UNAVAILABLE",
            "message": "FYERS rejected the read-only profile request. Check the local session and try again.",
        }
    except FyersReadOnlyError:
        return {
            "connected": False,
            "mode": "UNAVAILABLE",
            "message": "FYERS read-only client is unavailable or credentials are not configured.",
        }
    return {
        "connected": True,
        "mode": "READ_ONLY",
        "message": "FYERS profile check succeeded. This connection cannot place or manage orders.",
    }
