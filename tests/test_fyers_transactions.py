from decimal import Decimal

import pytest

from nifty_algo.brokers.fyers_readonly import FyersAPIError
from nifty_algo.brokers.fyers_transactions import (
    FyersCompliancePermit,
    FyersOrderTerms,
    FyersProductType,
    FyersTransactionAdapter,
    FyersTransactionBlocked,
)
from nifty_algo.brokers.protocol import OrderRequest, OrderSide, OrderType


def complete_permit():
    return FyersCompliancePermit(**{field: True for field in FyersCompliancePermit.__dataclass_fields__})


class CaptureTransport:
    def __init__(self, response=None):
        self.calls = []
        self.response = response or {"s": "ok", "code": 200, "id": "opaque-order"}

    def place_order(self, payload):
        self.calls.append(("place", dict(payload)))
        return self.response

    def modify_order(self, payload):
        self.calls.append(("modify", dict(payload)))
        return self.response

    def cancel_order(self, payload):
        self.calls.append(("cancel", dict(payload)))
        return self.response


def limit_request(*, side=OrderSide.BUY):
    return OrderRequest(
        client_order_id="client-1", signal_id="signal-1", symbol="NSE:TEST-EQ",
        side=side, quantity=2, order_type=OrderType.LIMIT, limit_price=Decimal("101.25"),
    )


def test_default_permit_fails_closed_before_transport_call():
    transport = CaptureTransport()
    adapter = FyersTransactionAdapter(transport)
    with pytest.raises(FyersTransactionBlocked, match="unverified requirements"):
        adapter.place_order(limit_request(), FyersOrderTerms(FyersProductType.INTRADAY))
    assert transport.calls == []


def test_limit_order_payload_uses_documented_fields_and_explicit_product():
    transport = CaptureTransport()
    adapter = FyersTransactionAdapter(transport, complete_permit())
    response = adapter.place_order(
        limit_request(side=OrderSide.SELL),
        FyersOrderTerms(FyersProductType.INTRADAY),
    )
    assert response["id"] == "opaque-order"
    assert transport.calls == [("place", {
        "symbol": "NSE:TEST-EQ", "qty": 2, "type": 1, "side": -1,
        "productType": "INTRADAY", "limitPrice": Decimal("101.25"),
        "stopPrice": Decimal("0"), "validity": "DAY", "disclosedQty": 0,
        "offlineOrder": False, "stopLoss": Decimal("0"), "takeProfit": Decimal("0"),
    })]


def test_market_order_is_rejected_even_with_complete_permit():
    market = OrderRequest(
        client_order_id="client-1", signal_id="signal-1", symbol="NSE:TEST-EQ",
        side=OrderSide.BUY, quantity=1, order_type=OrderType.MARKET,
    )
    transport = CaptureTransport()
    adapter = FyersTransactionAdapter(transport, complete_permit())
    with pytest.raises(FyersTransactionBlocked, match="only LIMIT"):
        adapter.place_order(market, FyersOrderTerms(FyersProductType.INTRADAY))
    assert transport.calls == []


def test_modify_and_cancel_payloads_match_official_sdk_examples():
    transport = CaptureTransport()
    adapter = FyersTransactionAdapter(transport, complete_permit())
    adapter.modify_order("broker-123", quantity=3, limit_price=Decimal("102.50"))
    adapter.cancel_order("broker-123")
    assert transport.calls == [
        ("modify", {"id": "broker-123", "type": 1, "limitPrice": Decimal("102.50"), "qty": 3}),
        ("cancel", {"id": "broker-123"}),
    ]


def test_invalid_terms_or_order_ids_are_rejected_without_transport():
    transport = CaptureTransport()
    adapter = FyersTransactionAdapter(transport, complete_permit())
    with pytest.raises(ValueError):
        adapter.modify_order(" ", quantity=1, limit_price=Decimal("1"))
    with pytest.raises(ValueError):
        adapter.modify_order("id", quantity=1, limit_price=Decimal("NaN"))
    with pytest.raises(ValueError):
        FyersOrderTerms(FyersProductType.INTRADAY, disclosed_quantity=-1)
    assert transport.calls == []


def test_error_response_is_redacted_and_success_is_not_claimed_as_fill():
    transport = CaptureTransport({"s": "error", "code": -8, "message": "secret-token"})
    adapter = FyersTransactionAdapter(transport, complete_permit())
    with pytest.raises(FyersAPIError) as caught:
        adapter.cancel_order("id")
    assert "secret-token" not in str(caught.value)
    assert "-8" in str(caught.value)

    success_transport = CaptureTransport()
    success_adapter = FyersTransactionAdapter(success_transport, complete_permit())
    acknowledgement = success_adapter.place_order(
        limit_request(), FyersOrderTerms(FyersProductType.INTRADAY)
    )
    assert "id" in acknowledgement
    # The adapter only returns the broker response; it does not synthesize a fill.
    assert "filled_quantity" not in acknowledgement


def test_transport_exception_text_is_redacted():
    class ExplodingTransport(CaptureTransport):
        def cancel_order(self, payload):
            raise RuntimeError("Authorization header contained secret-token")

    adapter = FyersTransactionAdapter(ExplodingTransport(), complete_permit())
    with pytest.raises(FyersAPIError) as caught:
        adapter.cancel_order("id")
    assert "secret-token" not in str(caught.value)
    assert caught.value.__cause__ is None
