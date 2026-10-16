"""Opt-in, read-only FYERS v3 facade.

The wrapped SDK object is deliberately private. This module exposes no order
placement, modification, cancellation, conversion, or position-exit methods.
No connection is created at import time.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol
from urllib.request import urlopen


class FyersReadOnlyError(RuntimeError):
    """Safe error type; messages never include response bodies or credentials."""


class FyersReadOnlyDisabled(FyersReadOnlyError):
    pass


class FyersAuthenticationError(FyersReadOnlyError):
    pass


class FyersAPIError(FyersReadOnlyError):
    def __init__(self, operation: str, code: str | None = None) -> None:
        self.operation = operation
        self.code = code
        suffix = f" (code {code})" if code else ""
        super().__init__(f"FYERS {operation} request failed{suffix}; response content was redacted")


@dataclass(frozen=True, slots=True)
class FyersReadCredentials:
    app_id: str = field(repr=False)
    access_token: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.app_id.strip() or not self.access_token.strip():
            raise ValueError("FYERS app ID and access token are required")

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> FyersReadCredentials:
        env = os.environ if environ is None else environ
        enabled = env.get("NIFTY_ALGO_FYERS_READONLY_ENABLED", "false").strip().lower()
        if enabled not in {"1", "true", "yes", "on"}:
            raise FyersReadOnlyDisabled("FYERS read-only connection is disabled")
        app_id = env.get("NIFTY_ALGO_FYERS_APP_ID", "")
        access_token = env.get("NIFTY_ALGO_FYERS_ACCESS_TOKEN", "")
        if not app_id.strip() or not access_token.strip():
            raise FyersAuthenticationError("FYERS read-only credentials are not configured")
        return cls(app_id=app_id, access_token=access_token)


class _ReadMethods(Protocol):
    def get_profile(self) -> Any: ...
    def funds(self) -> Any: ...
    def holdings(self) -> Any: ...
    def orderbook(self) -> Any: ...
    def tradebook(self) -> Any: ...
    def positions(self) -> Any: ...
    def quotes(self, data: dict[str, Any]) -> Any: ...
    def history(self, data: dict[str, Any]) -> Any: ...
    def depth(self, data: dict[str, Any]) -> Any: ...
    def optionchain(self, data: dict[str, Any]) -> Any: ...


class FyersReadOnlyClient:
    """Whitelist wrapper around an SDK-compatible client; does not log or persist data."""

    def __init__(self, sdk_client: _ReadMethods) -> None:
        self.__sdk_client = sdk_client

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> FyersReadOnlyClient:
        credentials = FyersReadCredentials.from_environment(environ)
        try:
            from fyers_apiv3 import fyersModel  # type: ignore[import-not-found]
        except ImportError as exc:
            raise FyersReadOnlyError("Optional FYERS SDK is missing; install the 'fyers' extra") from exc
        client = fyersModel.FyersModel(
            client_id=credentials.app_id,
            is_async=False,
            token=credentials.access_token,
            log_path="",
        )
        return cls(client)

    def get_profile(self) -> Mapping[str, Any]:
        return self._read("profile", self.__sdk_client.get_profile)

    def funds(self) -> Mapping[str, Any]:
        return self._read("funds", self.__sdk_client.funds)

    def holdings(self) -> Mapping[str, Any]:
        return self._read("holdings", self.__sdk_client.holdings)

    def orderbook(self) -> Mapping[str, Any]:
        return self._read("orderbook", self.__sdk_client.orderbook)

    def tradebook(self) -> Mapping[str, Any]:
        return self._read("tradebook", self.__sdk_client.tradebook)

    def positions(self) -> Mapping[str, Any]:
        return self._read("positions", self.__sdk_client.positions)

    def quotes(self, symbols: str) -> Mapping[str, Any]:
        if not symbols.strip():
            raise ValueError("at least one FYERS symbol is required")
        return self._read("quotes", lambda: self.__sdk_client.quotes({"symbols": symbols}))

    def history(self, parameters: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._read("history", lambda: self.__sdk_client.history(dict(parameters)))

    def depth(self, symbol: str, *, ohlcv_flag: str = "1") -> Mapping[str, Any]:
        if not symbol.strip():
            raise ValueError("FYERS symbol is required")
        return self._read("depth", lambda: self.__sdk_client.depth({"symbol": symbol, "ohlcv_flag": ohlcv_flag}))

    def option_chain(
        self,
        underlying: str,
        *,
        strike_count: int = 1,
        expiry_timestamp: int | None = None,
    ) -> Mapping[str, Any]:
        """Read an index option chain; this method cannot submit or modify orders."""
        if underlying not in {"NSE:NIFTY50-INDEX", "BSE:SENSEX-INDEX"}:
            raise ValueError("only NIFTY and SENSEX index chains are supported")
        if not 1 <= strike_count <= 50:
            raise ValueError("strike_count must be between 1 and 50")
        parameters: dict[str, Any] = {"symbol": underlying, "strikecount": strike_count}
        if expiry_timestamp is not None:
            if expiry_timestamp <= 0:
                raise ValueError("expiry_timestamp must be positive")
            parameters["timestamp"] = str(expiry_timestamp)
        return self._read("option chain", lambda: self.__sdk_client.optionchain(parameters))

    @staticmethod
    def _read(operation: str, call: Callable[[], Any]) -> Mapping[str, Any]:
        try:
            response = call()
        except Exception as exc:
            # Never chain SDK exceptions: upstream errors may include request headers/tokens.
            raise FyersAPIError(operation) from None
        if not isinstance(response, Mapping):
            raise FyersAPIError(operation)
        status = response.get("s")
        if status == "error" or (status is not None and status != "ok"):
            code = response.get("code")
            raise FyersAPIError(operation, str(code) if code is not None else None)
        return dict(response)


ALLOWED_SYMBOL_MASTERS = frozenset(
    {"NSE_CM", "NSE_FO", "NSE_CD", "NSE_COM", "BSE_CM", "BSE_FO", "MCX_COM"}
)


def load_symbol_master(
    master: str,
    *,
    fetch: Callable[[str], bytes] | None = None,
) -> Mapping[str, Any]:
    """Read an allowlisted FYERS public symbol-master JSON file; never accepts arbitrary URLs."""
    normalized = master.upper()
    if normalized not in ALLOWED_SYMBOL_MASTERS:
        raise ValueError("unsupported FYERS symbol master")
    url = f"https://public.fyers.in/sym_details/{normalized}_sym_master.json"
    fetch_bytes = _fetch_symbol_master if fetch is None else fetch
    try:
        payload = json.loads(fetch_bytes(url))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, UnicodeDecodeError):
        raise FyersAPIError("symbol master") from None
    if not isinstance(payload, (dict, list)):
        raise FyersAPIError("symbol master")
    return payload


def _fetch_symbol_master(url: str) -> bytes:
    # url is constructed solely from the allowlist above; response is bounded.
    with urlopen(url, timeout=10) as response:  # noqa: S310
        body = response.read(50_000_001)
    if len(body) > 50_000_000:
        raise ValueError("symbol master too large")
    return body
