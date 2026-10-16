"""Small, dependency-free domain models for the staged application."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class ExecutionMode(StrEnum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    LIVE = "LIVE"


class SignalDirection(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class ReferenceInstrument(StrEnum):
    UNDERLYING = "UNDERLYING"
    OPTION_PREMIUM = "OPTION_PREMIUM"


class OrderStatus(StrEnum):
    INTENT = "INTENT"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class PositionStatus(StrEnum):
    FLAT = "FLAT"
    OPENING = "OPENING"
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


@dataclass(frozen=True, slots=True)
class PriceLevel:
    value: Decimal
    reference: ReferenceInstrument
    symbol: str

    def __post_init__(self) -> None:
        if not self.value.is_finite() or self.value <= 0:
            raise ValueError("price level must be finite and greater than zero")
        if not self.symbol.strip():
            raise ValueError("price level symbol cannot be empty")


@dataclass(frozen=True, slots=True)
class Signal:
    signal_id: str
    direction: SignalDirection
    symbol: str
    timeframe: str
    bar_time: datetime
    entry_trigger: PriceLevel
    stop: PriceLevel
    reward_risk: Decimal

    def __post_init__(self) -> None:
        if not self.signal_id.strip():
            raise ValueError("signal_id cannot be empty")
        if not self.symbol.strip() or not self.timeframe.strip():
            raise ValueError("symbol and timeframe are required")
        if self.bar_time.tzinfo is None or self.bar_time.utcoffset() is None:
            raise ValueError("bar_time must be timezone-aware")
        if not self.reward_risk.is_finite() or self.reward_risk <= 0:
            raise ValueError("reward_risk must be finite and greater than zero")
        if self.entry_trigger.reference != self.stop.reference:
            raise ValueError("entry and stop must use the same reference instrument")
        if self.entry_trigger.symbol != self.stop.symbol:
            raise ValueError("entry and stop must refer to the same symbol")


@dataclass(frozen=True, slots=True)
class RiskDecision:
    permitted: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Order:
    order_id: str
    signal_id: str
    status: OrderStatus
    requested_quantity: int
    filled_quantity: int = 0

    def __post_init__(self) -> None:
        if not self.order_id.strip() or not self.signal_id.strip():
            raise ValueError("order_id and signal_id are required")
        if self.requested_quantity <= 0:
            raise ValueError("requested_quantity must be positive")
        if not 0 <= self.filled_quantity <= self.requested_quantity:
            raise ValueError("filled_quantity must be between zero and requested quantity")


@dataclass(frozen=True, slots=True)
class Fill:
    fill_id: str
    order_id: str
    quantity: int
    price: Decimal
    filled_at: datetime

    def __post_init__(self) -> None:
        if not self.fill_id.strip() or not self.order_id.strip():
            raise ValueError("fill_id and order_id are required")
        if self.quantity <= 0 or not self.price.is_finite() or self.price <= 0:
            raise ValueError("fill quantity and price must be positive")
        if self.filled_at.tzinfo is None or self.filled_at.utcoffset() is None:
            raise ValueError("filled_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Position:
    position_id: str
    symbol: str
    status: PositionStatus
    quantity: int
    average_entry_price: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.position_id.strip() or not self.symbol.strip():
            raise ValueError("position_id and symbol are required")
        if self.quantity < 0:
            raise ValueError("position quantity cannot be negative")
        if self.average_entry_price is not None and (
            not self.average_entry_price.is_finite() or self.average_entry_price <= 0
        ):
            raise ValueError("average_entry_price must be positive when supplied")


@dataclass(frozen=True, slots=True)
class Contract:
    symbol: str
    expiry: datetime
    strike: Decimal
    option_type: str
    lot_size: int

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("contract symbol cannot be empty")
        if self.expiry.tzinfo is None or self.expiry.utcoffset() is None:
            raise ValueError("contract expiry must be timezone-aware")
        if not self.strike.is_finite() or self.strike <= 0:
            raise ValueError("contract strike must be positive")
        if self.option_type not in {"CE", "PE"}:
            raise ValueError("option_type must be CE or PE")
        if self.lot_size <= 0:
            raise ValueError("lot_size must be positive")
