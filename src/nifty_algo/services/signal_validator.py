"""Strict schema validation for the supplied Pine alert contract."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TradingViewAlert(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    alert_id: str = Field(min_length=1, max_length=256)
    action: Literal["LONG", "SHORT"]
    underlying: str = Field(min_length=1, max_length=128)
    entry_trigger: Decimal
    sl_underlying: Decimal
    rr: Decimal
    schema_version: Literal[1] | None = None
    strategy_id: str | None = None
    strategy_version: str | None = None
    event_type: Literal["ENTRY_SIGNAL"] | None = None
    timeframe: Literal["5"] | None = None
    reference_instrument: Literal["CHART_SYMBOL"] | None = None
    price_unit: Literal["CHART_PRICE"] | None = None
    bar_time_epoch_ms: int | None = Field(default=None, gt=0)
    emitted_at_epoch_ms: int | None = Field(default=None, gt=0)
    target_price: Decimal | None = None

    @field_validator("entry_trigger", "sl_underlying", "rr", "target_price")
    @classmethod
    def finite_positive_values(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("value must be finite and greater than zero")
        return value

    @field_validator("underlying")
    @classmethod
    def valid_underlying(cls, value: str) -> str:
        if not value or len(value) > 128:
            raise ValueError("underlying is invalid")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("underlying cannot contain control characters")
        if "NIFTY" not in value.upper():
            raise ValueError("only NIFTY index signals are supported")
        return value

    @field_validator("alert_id")
    @classmethod
    def valid_alert_id(cls, value: str) -> str:
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("alert_id cannot contain control characters")
        return value

    @model_validator(mode="after")
    def levels_match_direction(self) -> "TradingViewAlert":
        if self.action == "LONG" and self.entry_trigger <= self.sl_underlying:
            raise ValueError("LONG entry_trigger must be above sl_underlying")
        if self.action == "SHORT" and self.entry_trigger >= self.sl_underlying:
            raise ValueError("SHORT entry_trigger must be below sl_underlying")
        if self.rr != Decimal("3.0"):
            raise ValueError("rr must match the Pine strategy's fixed 3R target")
        versioned = (
            self.strategy_id,
            self.strategy_version,
            self.event_type,
            self.timeframe,
            self.reference_instrument,
            self.price_unit,
            self.bar_time_epoch_ms,
            self.emitted_at_epoch_ms,
            self.target_price,
        )
        if self.schema_version is None:
            if any(value is not None for value in versioned):
                raise ValueError("versioned fields require schema_version=1")
        else:
            if any(value is None for value in versioned):
                raise ValueError("schema_version=1 requires the complete v1 contract")
            if self.strategy_id != "MAYUR_VDBT_RR":
                raise ValueError("strategy_id is not recognized")
            if self.action == "LONG" and self.target_price <= self.entry_trigger:
                raise ValueError("LONG target_price must be above entry_trigger")
            if self.action == "SHORT" and self.target_price >= self.entry_trigger:
                raise ValueError("SHORT target_price must be below entry_trigger")
        return self


def validate_alert(payload: object) -> TradingViewAlert:
    return TradingViewAlert.model_validate(payload)
