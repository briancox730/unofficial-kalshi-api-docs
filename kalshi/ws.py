"""Async Kalshi WebSocket client (orderbook + fills).

Protocol summary (see docs/websocket.md):
  * URL:  wss://api.elections.kalshi.com/trade-api/ws/v2  (demo: demo-api.kalshi.co)
  * Auth: the SAME three RSA-PSS headers as REST, signed over GET /trade-api/ws/v2,
    sent on the HTTP upgrade request.
  * Subscribe: {"id", "cmd":"subscribe", "params":{"channels":[...], "market_tickers":[...]}}
  * Frames: {"type", "seq", "msg"} where type is one of:
      subscribed | orderbook_snapshot | orderbook_delta | fill | error
  * `seq` is a per-connection monotonic counter — a gap means you missed a frame
    (reconnect / resubscribe to resync).

This client maintains an `OrderBook` per ticker and yields decoded frames. It is
deliberately small and has no trading logic.
"""
import asyncio
import contextlib
import itertools
import json

import websockets

from .auth import auth_headers
from .orderbook import OrderBook

WS_URLS = {
    "prod": "wss://api.elections.kalshi.com/trade-api/ws/v2",
    "demo": "wss://demo-api.kalshi.co/trade-api/ws/v2",
}
WS_SIGN_PATH = "/trade-api/ws/v2"


async def _connect(url, headers):
    """websockets >=13 takes `additional_headers`; older takes `extra_headers`."""
    try:
        return await websockets.connect(url, additional_headers=headers)
    except TypeError:
        return await websockets.connect(url, extra_headers=headers)


class KalshiWsClient:
    def __init__(self, api_key, private_key, env="demo"):
        self.api_key = api_key
        self.private_key = private_key
        self.url = WS_URLS[env]
        self.ws = None
        self._ids = itertools.count(1)
        self.books = {}  # ticker -> OrderBook
        self._last_seq = None

    async def connect(self):
        headers = auth_headers(self.api_key, self.private_key, "GET", WS_SIGN_PATH)
        self.ws = await _connect(self.url, headers)
        return self

    async def __aenter__(self):
        return await self.connect()

    async def __aexit__(self, *exc):
        await self.close()

    async def close(self):
        if self.ws is not None:
            with contextlib.suppress(Exception):
                await self.ws.close()
            self.ws = None

    async def _send(self, payload):
        await self.ws.send(json.dumps(payload))

    async def subscribe(self, channels, market_tickers=None):
        """Subscribe to one or more channels.

        `orderbook_delta` auto-sends a snapshot first. `fill` is account-wide and
        takes no market_tickers.
        """
        params = {"channels": channels}
        if market_tickers:
            params["market_tickers"] = market_tickers
        await self._send({"id": next(self._ids), "cmd": "subscribe", "params": params})

    async def update_subscription(self, sids, action, market_tickers):
        """Add or remove markets on an existing subscription without reconnecting.

        action: "add_markets" | "delete_markets".
        """
        await self._send({
            "id": next(self._ids),
            "cmd": "update_subscription",
            "params": {"sids": sids, "action": action, "market_tickers": market_tickers},
        })

    async def messages(self):
        """Yield decoded frames as dicts: {"type", "seq", "msg"}.

        Side effect: orderbook_snapshot / orderbook_delta frames are applied to
        `self.books[ticker]` before yielding, so you can read the live book.
        `websockets` answers server pings for you.
        """
        async for raw in self.ws:
            frame = json.loads(raw)
            ftype = frame.get("type")
            seq = frame.get("seq")
            if seq is not None:
                if self._last_seq is not None and seq != self._last_seq + 1:
                    frame["seq_gap"] = (self._last_seq, seq)  # caller may resubscribe
                self._last_seq = seq

            msg = frame.get("msg") or {}
            if ftype == "orderbook_snapshot":
                book = self.books.setdefault(msg.get("market_ticker"), OrderBook(msg.get("market_ticker")))
                book.apply_snapshot(msg.get("yes_dollars_fp"), msg.get("no_dollars_fp"))
            elif ftype == "orderbook_delta":
                book = self.books.setdefault(msg.get("market_ticker"), OrderBook(msg.get("market_ticker")))
                book.apply_delta(msg.get("side"), msg.get("price_dollars"), msg.get("delta_fp"))

            yield frame


async def stream_orderbook(api_key, private_key, tickers, env="demo", reconnect=True):
    """Convenience generator: yield (ticker, OrderBook) on every book change.

    Reconnects with simple exponential backoff and resubscribes on a seq gap.
    """
    backoff = 1.0
    while True:
        try:
            async with KalshiWsClient(api_key, private_key, env=env) as client:
                await client.subscribe(["orderbook_delta"], market_tickers=tickers)
                backoff = 1.0  # healthy again
                async for frame in client.messages():
                    if frame.get("seq_gap"):
                        # Missed a frame; resync by resubscribing.
                        await client.subscribe(["orderbook_delta"], market_tickers=tickers)
                    if frame.get("type") in ("orderbook_snapshot", "orderbook_delta"):
                        ticker = (frame.get("msg") or {}).get("market_ticker")
                        if ticker in client.books:
                            yield ticker, client.books[ticker]
        except Exception as exc:  # noqa: BLE001 — demo helper; surface + retry
            if not reconnect:
                raise
            print(f"[ws] disconnected ({exc!r}); reconnecting in {backoff:.0f}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
