import json

import pytest

from nifty_algo.brokers.fyers_readonly import (
    FyersAPIError,
    FyersAuthenticationError,
    FyersReadCredentials,
    FyersReadOnlyClient,
    FyersReadOnlyDisabled,
    load_symbol_master,
)


class FakeFyers:
    def __init__(self):
        self.calls = []

    def _call(self, name, *args):
        self.calls.append((name, args))
        return {"s": "ok", "data": name}

    def get_profile(self): return self._call("get_profile")
    def funds(self): return self._call("funds")
    def holdings(self): return self._call("holdings")
    def orderbook(self): return self._call("orderbook")
    def tradebook(self): return self._call("tradebook")
    def positions(self): return self._call("positions")
    def quotes(self, data): return self._call("quotes", data)
    def history(self, data): return self._call("history", data)
    def depth(self, data): return self._call("depth", data)
    def place_order(self, *_args, **_kwargs): raise AssertionError("write API must not be called")


def test_read_methods_are_whitelisted_and_arguments_match_sdk_contract():
    fake = FakeFyers()
    client = FyersReadOnlyClient(fake)
    assert client.get_profile() == {"s": "ok", "data": "get_profile"}
    client.quotes("NSE:NIFTY50-INDEX")
    client.history({"symbol": "NSE:NIFTY50-INDEX", "resolution": "1"})
    client.depth("NSE:NIFTY50-INDEX")
    assert fake.calls == [
        ("get_profile", ()),
        ("quotes", ({"symbols": "NSE:NIFTY50-INDEX"},)),
        ("history", ({"symbol": "NSE:NIFTY50-INDEX", "resolution": "1"},)),
        ("depth", ({"symbol": "NSE:NIFTY50-INDEX", "ohlcv_flag": "1"},)),
    ]
    assert not hasattr(client, "place_order")
    assert not hasattr(client, "cancel_order")


def test_environment_gate_is_off_by_default_and_requires_credentials():
    with pytest.raises(FyersReadOnlyDisabled):
        FyersReadCredentials.from_environment({})
    with pytest.raises(FyersAuthenticationError):
        FyersReadCredentials.from_environment({"NIFTY_ALGO_FYERS_READONLY_ENABLED": "true"})
    credentials = FyersReadCredentials.from_environment({
        "NIFTY_ALGO_FYERS_READONLY_ENABLED": "true",
        "NIFTY_ALGO_FYERS_APP_ID": "app",
        "NIFTY_ALGO_FYERS_ACCESS_TOKEN": "top-secret-token",
    })
    assert "top-secret-token" not in repr(credentials)


def test_errors_redact_upstream_response_and_exception_text():
    class Broken(FakeFyers):
        def get_profile(self):
            raise RuntimeError("Authorization: top-secret-token")

    with pytest.raises(FyersAPIError) as error:
        FyersReadOnlyClient(Broken()).get_profile()
    assert "top-secret-token" not in str(error.value)
    assert error.value.__cause__ is None

    class Rejected(FakeFyers):
        def funds(self):
            return {"s": "error", "code": -8, "message": "top-secret-token"}

    with pytest.raises(FyersAPIError) as rejected:
        FyersReadOnlyClient(Rejected()).funds()
    assert "-8" in str(rejected.value)
    assert "top-secret-token" not in str(rejected.value)


def test_symbol_master_is_allowlisted_and_json_is_injectable():
    seen = []
    result = load_symbol_master("nse_fo", fetch=lambda url: seen.append(url) or json.dumps({"sample": {"symTicker": "NSE:TEST"}}).encode())
    assert result["sample"]["symTicker"] == "NSE:TEST"
    assert seen == ["https://public.fyers.in/sym_details/NSE_FO_sym_master.json"]
    with pytest.raises(ValueError):
        load_symbol_master("https://attacker.invalid/data", fetch=lambda _url: b"{}")


def test_symbol_master_rejects_malformed_payload_without_leaking_body():
    with pytest.raises(FyersAPIError):
        load_symbol_master("NSE_CM", fetch=lambda _url: b'"not-an-object"')
