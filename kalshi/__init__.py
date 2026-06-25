"""unofficial-kalshi-api-docs: a small, market-agnostic Kalshi API client.

This package documents and demonstrates the Kalshi trading API. It contains no
trading strategy — just the mechanics of talking to the API correctly.

    from kalshi import KalshiHttpClient
    client = KalshiHttpClient.from_env()      # reads KALSHI_* env vars
    print(client.balance())
"""
__version__ = "0.1.0"  # keep in sync with pyproject.toml

from .auth import auth_headers, load_private_key, sign
from .client import (
    BASE_URLS,
    STP_TAKER_AT_CROSS,
    KalshiError,
    KalshiHttpClient,
    fp,
    normalize_order_response,
    our_fill_price,
    position_contracts,
    synth_status,
    to_v2_order_body,
)
from .orderbook import OrderBook
from .ws import WS_URLS, KalshiWsClient, stream_orderbook

__all__ = [
    "KalshiHttpClient",
    "KalshiError",
    "BASE_URLS",
    "STP_TAKER_AT_CROSS",
    "OrderBook",
    "KalshiWsClient",
    "stream_orderbook",
    "WS_URLS",
    "auth_headers",
    "load_private_key",
    "sign",
    "fp",
    "position_contracts",
    "to_v2_order_body",
    "our_fill_price",
    "synth_status",
    "normalize_order_response",
]
