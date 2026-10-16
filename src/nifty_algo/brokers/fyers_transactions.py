"""Fail-closed FYERS v3 transaction adapter and SDK transport.

Network methods are available only behind an explicit local transaction toggle,
and every write still passes the default-deny compliance permit. This module is
not wired to signal intake or the dashboard's read-only order manager.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal
from enum import StrEnum
import os
from typing import Any, Callable, Mapping, Protocol

from nifty_algo.brokers.fyers_readonly import FyersAPIError
from nifty_algo.brokers.protocol import OrderRequest, OrderSide, OrderType
from nifty_algo.config import AppConfig
from nifty_algo.domain.models import ExecutionMode


class FyersTransactionBlocked(RuntimeError):
    """Transaction is blocked because required account/compliance facts are unverified."""


@dataclass(frozen=True, slots=True)
class FyersCompliancePermit:
    """Explicit per-session checklist; defaults fail closed and is not env-loadable."""

    app_activation_verified: bool = False
    static_ip_verified: bool = False
    daily_2fa_complete: bool = False
    topology_approved_by_fyers: bool = False
    strategy_registration_or_generic_tagging_confirmed: bool = False
    instrument_and_order_types_confirmed: bool = False
    rate_limits_and_broker_rms_confirmed: bool = False
    account_compliance_review_complete: bool = False
    operator_armed: bool = False

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(item.name for item in fields(self) if not getattr(self, item.name))

    def assert_ready(self) -> None:
        if self.missing:
            raise FyersTransactionBlocked(
                "FYERS transactions blocked; unverified requirements: " + ", ".join(self.missing)
            )


class FyersProductType(StrEnum):
    CNC = "CNC"
    INTRADAY = "INTRADAY"
    MARGIN = "MARGIN"
    CO = "CO"
    BO = "BO"
    MTF = "MTF"


@dataclass(frozen=True, slots=True)
class FyersOrderTerms:
    """Explicit FYERS-specific fields; no strategy or product defaults are inferred."""

    product_type: FyersProductType
    disclosed_quantity: int = 0
    stop_price: Decimal = Decimal("0")
    stop_loss: Decimal = Decimal("0")
    take_profit: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.disclosed_quantity < 0:
            raise ValueError("disclosed quantity cannot be negative")
        for name in ("stop_price", "stop_loss", "take_profit"):
            value = getattr(self, name)
            if not value.is_finite() or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")


class FyersTransactionTransport(Protocol):
    """Injectable FYERS transaction transport boundary."""

    def place_order(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def modify_order(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def cancel_order(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


class FyersSDKTransactionTransport:
    """Thin FYERS v3 SDK write transport; use only through the guarded adapter.

    The environment toggle is an additional off-by-default guard, not evidence
    that the account, network, strategy, or order is live-ready. The adapter's
    compliance permit remains independently required for every operation.
    """

    def __init__(self, sdk_client: Any, permit: FyersCompliancePermit, config: AppConfig) -> None:
        self.__sdk_client = sdk_client
        self.__permit = permit
        self.__config = config
        self._assert_live_ready()

    @classmethod
    def from_environment(
        cls,
        permit: FyersCompliancePermit,
        config: AppConfig,
        environ: Mapping[str, str] | None = None,
    ) -> FyersSDKTransactionTransport:
        permit.assert_ready()
        if config.execution_mode is not ExecutionMode.LIVE:
            raise FyersTransactionBlocked("FYERS transaction transport requires LIVE mode")
        try:
            config.assert_live_ready()
        except ValueError:
            raise FyersTransactionBlocked("application live-risk safeguards are not satisfied") from None
        source = os.environ if environ is None else environ
        enabled = source.get("NIFTY_ALGO_FYERS_TRANSACTIONS_ENABLED", "false").strip().lower()
        if enabled not in {"1", "true", "yes", "on"}:
            raise FyersTransactionBlocked("FYERS transaction transport is disabled")
        app_id = source.get("NIFTY_ALGO_FYERS_APP_ID", "").strip()
        access_token = source.get("NIFTY_ALGO_FYERS_ACCESS_TOKEN", "").strip()
        if not app_id or not access_token:
            raise FyersTransactionBlocked("FYERS transaction credentials are not configured")
        try:
            from fyers_apiv3 import fyersModel  # type: ignore[import-not-found]
        except ImportError:
            raise FyersTransactionBlocked("FYERS SDK is unavailable") from None
        try:
            client = fyersModel.FyersModel(
                client_id=app_id,
                is_async=False,
                token=access_token,
                log_path="",
            )
        except Exception:
            raise FyersTransactionBlocked("FYERS client could not be initialized") from None
        return cls(client, permit, config)

    def _assert_live_ready(self) -> None:
        self.__permit.assert_ready()
        if self.__config.execution_mode is not ExecutionMode.LIVE:
            raise FyersTransactionBlocked("FYERS transaction transport requires LIVE mode")
        try:
            self.__config.assert_live_ready()
        except ValueError:
            raise FyersTransactionBlocked("application live-risk safeguards are not satisfied") from None

    def place_order(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self._assert_live_ready()
        return self._call("place order", lambda: self.__sdk_client.place_order(dict(payload)))

    def modify_order(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self._assert_live_ready()
        return self._call("modify order", lambda: self.__sdk_client.modify_order(dict(payload)))

    def cancel_order(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self._assert_live_ready()
        return self._call("cancel order", lambda: self.__sdk_client.cancel_order(dict(payload)))

    @staticmethod
    def _call(operation: str, call: Callable[[], Any]) -> Mapping[str, Any]:
        try:
            result = call()
        except Exception:
            # SDK exception strings can contain request details; redact them.
            raise FyersAPIError(operation) from None
        if not isinstance(result, Mapping):
            raise FyersAPIError(operation)
        status = result.get("s")
        if status == "error" or (status is not None and status != "ok"):
            code = result.get("code")
            raise FyersAPIError(operation, str(code) if code is not None else None)
        return dict(result)


class FyersTransactionAdapter:
    """Schema adapter whose default permit blocks all transactions."""

    def __init__(
        self,
        transport: FyersTransactionTransport,
        permit: FyersCompliancePermit | None = None,
    ) -> None:
        self.__transport = transport
        self.__permit = permit or FyersCompliancePermit()

    def place_order(self, request: OrderRequest, terms: FyersOrderTerms) -> Mapping[str, Any]:
        self.__permit.assert_ready()
        payload = self.build_order_payload(request, terms)
        return self._invoke("place order", lambda: self.__transport.place_order(payload))

    def modify_order(
        self,
        order_id: str,
        *,
        quantity: int,
        limit_price: Decimal,
    ) -> Mapping[str, Any]:
        self.__permit.assert_ready()
        if not order_id.strip():
            raise ValueError("FYERS order ID is required")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if not limit_price.is_finite() or limit_price <= 0:
            raise ValueError("limit price must be finite and positive")
        payload = {"id": order_id, "type": 1, "limitPrice": limit_price, "qty": quantity}
        return self._invoke("modify order", lambda: self.__transport.modify_order(payload))

    def cancel_order(self, order_id: str) -> Mapping[str, Any]:
        self.__permit.assert_ready()
        if not order_id.strip():
            raise ValueError("FYERS order ID is required")
        return self._invoke("cancel order", lambda: self.__transport.cancel_order({"id": order_id}))

    @staticmethod
    def build_order_payload(request: OrderRequest, terms: FyersOrderTerms) -> dict[str, Any]:
        # NSE's retail-algo FAQ prohibits market orders; only LIMIT maps here.
        if request.order_type is not OrderType.LIMIT:
            raise FyersTransactionBlocked("only LIMIT orders are supported by this transaction contract")
        if request.limit_price is None:
            raise ValueError("LIMIT order requires limit_price")
        if request.quantity <= 0:
            raise ValueError("quantity must be positive")
        return {
            "symbol": request.symbol,
            "qty": request.quantity,
            "type": 1,
            "side": 1 if request.side is OrderSide.BUY else -1,
            "productType": terms.product_type.value,
            "limitPrice": request.limit_price,
            "stopPrice": terms.stop_price,
            "validity": "DAY",
            "disclosedQty": terms.disclosed_quantity,
            "offlineOrder": False,
            "stopLoss": terms.stop_loss,
            "takeProfit": terms.take_profit,
        }

    @staticmethod
    def _invoke(operation: str, call: Callable[[], Any]) -> Mapping[str, Any]:
        try:
            response = call()
        except Exception:
            raise FyersAPIError(operation) from None
        if not isinstance(response, Mapping):
            raise FyersAPIError(operation)
        status = response.get("s")
        if status == "error" or (status is not None and status != "ok"):
            code = response.get("code")
            raise FyersAPIError(operation, str(code) if code is not None else None)
        return dict(response)
