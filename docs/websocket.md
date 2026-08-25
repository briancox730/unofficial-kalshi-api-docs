# WebSocket

The WS API streams orderbook updates and your fills. Implemented in `kalshi/ws.py`;
runnable examples are `examples/06_stream_orderbook_ws.py` and
`examples/07_stream_fills_ws.py`.

## Connect & authenticate

- URL: `wss://api.elections.kalshi.com/trade-api/ws/v2` (demo:
  `wss://demo-api.kalshi.co/trade-api/ws/v2`).
- Auth: the **same three RSA-PSS headers as REST**, sent on the HTTP upgrade
  request, signed over `GET /trade-api/ws/v2`:

```python
from kalshi.auth import auth_headers
hdrs = auth_headers(api_key, private_key, "GET", "/trade-api/ws/v2")
# websockets >= 13: connect(url, additional_headers=hdrs)
# websockets <  13: connect(url, extra_headers=hdrs)
```

## Subscribe

Send a JSON command after the connection opens:

```json
{
  "id": 1,
  "cmd": "subscribe",
  "params": {
    "channels": ["orderbook_delta"],
    "market_tickers": ["TICKER1", "TICKER2"]
  }
}
```

- `id` — your command id (increment per command).
- `channels` — e.g. `["orderbook_delta"]`. Subscribing to `orderbook_delta`
  auto-sends an `orderbook_snapshot` first.
- `market_tickers` — required for orderbook channels; omit for `fill`.

Add/remove markets without reconnecting:

```json
{ "id": 2, "cmd": "update_subscription",
  "params": { "sids": [<sid>], "action": "add_markets" | "delete_markets",
              "market_tickers": ["TICKER3"] } }
```

## Frames

Every frame is `{ "type": ..., "seq": <int?>, "msg": {...} }`.

`seq` is a **per-connection monotonic counter**. A gap (`seq != last + 1`) means
you missed a frame — reconnect or resubscribe to resync.

### `subscribed`
`msg`: `{ "sid": <int>, "channel": "orderbook_delta" }`. Keep `sid` for
`update_subscription`.

### `orderbook_snapshot`
```json
{ "type": "orderbook_snapshot", "seq": 12,
  "msg": { "market_ticker": "…",
           "yes_dollars_fp": [["0.62", 12.5], ["0.61", 8.0]],
           "no_dollars_fp":  [["0.38", 15.0]] } }
```
Each row is `[price_dollars, size]`. **Bids only**; derive asks as the complement
(`yes_ask = 1 - best_no_bid`).

### `orderbook_delta`
```json
{ "type": "orderbook_delta", "seq": 13,
  "msg": { "market_ticker": "…", "side": "yes",
           "price_dollars": "0.62", "delta_fp": "-3.5" } }
```
`delta_fp` is a **change** in size (can be negative, fractional). **Accumulate
exactly**; drop a level when its size nets to ~0. (See gotcha #9.)

### `fill` (account channel — subscribe `["fill"]`, no tickers)
```json
{ "type": "fill",
  "msg": { "market_ticker": "…", "side": "yes", "action": "buy",
           "yes_price_dollars": "0.750", "no_price_dollars": "0.250",
           "count_fp": "1.00", "is_taker": true,
           "post_position_fp": "1.00", "ts_ms": 1717200000000 } }
```
`post_position_fp` is your signed position **after** the fill. This channel is the
source of truth for executions — and, since Kalshi's V2 order API dropped the
single-order GET, it is the recommended way to detect fills on **resting** orders
(the REST fallback is `GET /portfolio/fills`). The `fill` channel is **unaffected**
by the v1→v2 order-endpoint migration; see [gotchas.md](gotchas.md) #1.

### `error`
`msg`: `{ "code": <int>, "msg": "…" }`.

## Field encoding

- Prices/sizes are **string-or-number** (`0.62` or `"0.62"`) — parse both.
- WS prices are in **dollars** (`*_dollars_fp`, `price_dollars`); REST orderbook
  prices are in **cents**. Don't mix them.
- Keep prices in integer "mills" (price × 1000) to preserve 0.001 deci-cent ticks.

## Heartbeat & reconnect

- The server may send WebSocket pings; the `websockets` library auto-replies with
  pongs.
- Use a wire-staleness timeout (no frame at all for N seconds → reconnect) and,
  if you only care about a market that can go quiet, a data-staleness timeout
  (no snapshot/delta for M minutes → reconnect).
- Reconnect with exponential backoff; on a `seq` gap, resubscribe to resync.
`kalshi.stream_orderbook()` shows a minimal version of this.
