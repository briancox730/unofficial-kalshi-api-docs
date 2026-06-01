"""unofficial-kalshi-api-docs: a small, market-agnostic Kalshi API client.

This package documents and demonstrates the Kalshi trading API. It contains no
trading strategy — just the mechanics of talking to the API correctly.

    from kalshi import KalshiHttpClient
    client = KalshiHttpClient.from_env()      # reads KALSHI_* env vars
    print(client.balance())
"""
from .auth import auth_headers, load_private_key, sign
from .client import (
    BASE_URLS,
    KalshiError,
    KalshiHttpClient,
    fp,
    position_contracts,
    sell_proceeds,
)
from .orderbook import OrderBook
from .ws import WS_URLS, KalshiWsClient, stream_orderbook

__all__ = [
    "KalshiHttpClient",
    "KalshiError",
    "BASE_URLS",
    "OrderBook",
    "KalshiWsClient",
    "stream_orderbook",
    "WS_URLS",
    "auth_headers",
    "load_private_key",
    "sign",
    "fp",
    "position_contracts",
    "sell_proceeds",
]
