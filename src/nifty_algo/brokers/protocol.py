"""Broker-neutral order messages; no network or broker SDK imports live here."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, Sequence

from nifty_algo.domain.models import ExecutionMode, OrderStatus


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass(frozen=True, slots=True)
class OrderRequest:
    client_order_id: str
    signal_id: str
    symbol: str
    side: OrderSide
    quantity: int
    order_type: OrderType
    limit_price: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.client_order_id.strip() or not self.signal_id.strip() or not self.symbol.strip():
            raise ValueError("client_order_id, signal_id and symbol are required")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.order_type is OrderType.LIMIT:
            if self.limit_price is None or not self.limit_price.is_finite() or self.limit_price <= 0:
                raise ValueError("LIMIT orders require a finite positive limit_price")
        elif self.limit_price is not None:
            raise ValueError("MARKET orders cannot include limit_price")


@dataclass(frozen=True, slots=True)
class BrokerAcknowledgement:
    client_order_id: str
    broker_order_id: str
    status: OrderStatus
    message_code: str | None = None


@dataclass(frozen=True, slots=True)
class BrokerExecution:
    execution_id: str
    client_order_id: str
    quantity: int
    price: Decimal
    executed_at: datetime

    def __post_init__(self) -> None:
        if not self.execution_id.strip() or not self.client_order_id.strip():
            raise ValueError("execution_id and client_order_id are required")
        if self.quantity <= 0 or not self.price.is_finite() or self.price <= 0:
            raise ValueError("execution quantity and price must be positive")
        if self.executed_at.tzinfo is None or self.executed_at.utcoffset() is None:
            raise ValueError("executed_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class BrokerOrderSnapshot:
    client_order_id: str
    broker_order_id: str
    status: OrderStatus
    requested_quantity: int
    filled_quantity: int
    average_fill_price: Decimal | None


@dataclass(frozen=True, slots=True)
class BrokerPositionSnapshot:
    symbol: str
    net_quantity: int
    average_price: Decimal | None


class AmbiguousBrokerOutcome(RuntimeError):
    """The submit/cancel outcome is unknown; never retry without reconciliation."""


class BrokerPort(Protocol):
    mode: ExecutionMode

    def submit(self, request: OrderRequest) -> BrokerAcknowledgement: ...

    def cancel(self, client_order_id: str) -> BrokerOrderSnapshot: ...

    def list_orders(self) -> Sequence[BrokerOrderSnapshot]: ...

    def list_executions(self) -> Sequence[BrokerExecution]: ...

    def list_positions(self) -> Sequence[BrokerPositionSnapshot]: ...
