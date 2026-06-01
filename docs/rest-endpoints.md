# REST endpoints

All paths are under the `/trade-api/v2` prefix. All require the three auth
headers (see [authentication.md](authentication.md)). Base URLs in
[authentication.md](authentication.md). Examples use the `KalshiHttpClient` in
`kalshi/client.py`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/exchange/status` | is the exchange / trading open |
| GET | `/portfolio/balance` | cash balance (cents) |
| GET | `/markets` | list markets (paginated) |
| GET | `/markets/{ticker}` | one market |
| GET | `/markets/{ticker}/orderbook` | bids-only book |
| GET | `/portfolio/positions` | your open positions |
| POST | `/portfolio/orders` | place an order |
| GET | `/portfolio/orders/{id}` | poll an order |
| DELETE | `/portfolio/orders/{id}` | cancel (reduce) an order |

---

## GET /exchange/status
`{ "exchange_active": bool, "trading_active": bool }`

## GET /portfolio/balance
`{ "balance": <cents int>, "payout": <cents int> }` — `payout` is the reserve held
against open positions.

## GET /markets
Query params: `series_ticker`, `status` (`open` | `closed` | `settled` — **not**
`active`), `limit` (max 1000), `cursor`. Returns `{ "markets": [...], "cursor": "" }`
(`cursor` empty = last page).

Each market: `ticker`, `event_ticker`, `series_ticker`, `status`, `yes_bid`,
`yes_ask`, `no_bid`, `no_ask` (cents, may be `null` for illiquid strikes),
`last_price`, `open_time`, `close_time` (ISO), `title`.

> Gotcha: just after a market settles, `?status=open` can list it first for ~30s.
> Sort by soonest-future `close_time` rather than taking `markets[0]`.

## GET /markets/{ticker}/orderbook
`{ "orderbook": { "yes": [[price_cents, count], ...], "no": [[...], ...] } }`
(sometimes the bare `{ "yes": ..., "no": ... }` without the wrapper).

**Bids only**, best (highest) first. Derive asks:
`yes_ask = 100 - best_no_bid`, `no_ask = 100 - best_yes_bid`.

## GET /portfolio/positions
Always query with `count_filter=position` (drops flat rows; Kalshi keeps a row
for every market you ever touched). Optional `ticker`. Returns
`{ "market_positions": [...], "event_positions": [...], "cursor": "" }`.

Each `market_position`: `ticker`, `position_fp` (**signed** string: + = yes,
− = no), `market_exposure_dollars`, `realized_pnl_dollars`, `total_traded_dollars`,
`fees_paid_dollars`, `last_updated_ts` (**ISO string, not int**),
`resting_orders_count`.

> Gotcha: this endpoint **lags fills ~1s** and returns the pre-order state. Poll.

## POST /portfolio/orders
Request body:

```jsonc
{
  "ticker": "…",
  "side": "yes" | "no",            // which contract
  "action": "buy" | "sell",
  "count": 1,                      // whole contracts
  "time_in_force": "immediate_or_cancel" | "good_till_canceled" | "fill_or_kill",
  "client_order_id": "uuid",       // idempotency key
  // price: ONE of these per side —
  "yes_price": 60,                 // integer cents 1-99
  "no_price": 40,
  "yes_price_dollars": "0.9980",   // OR sub-cent dollars string
  "no_price_dollars": "0.0020",
  "post_only": true                // optional: reject if it would take liquidity
}
```

Returns `{ "order": <Order> }`. The `Order` includes `order_id`, `status`
(`resting` | `executed` | `canceled`), `outcome_side`, `action`, the `_fp` count
fields (`fill_count_fp`, `remaining_count_fp`, `initial_count_fp`), and the cost
fields (`taker_fill_cost_dollars`, `taker_fees_dollars`, `maker_*`).

> Gotchas: a **sell** is reported on the complement side (proceeds =
> `1 - taker_fill_cost/fill_count`); to **close**, sell the held side with integer
> cents (see gotchas #1, #2, #3). IOC can fill even against an empty-looking book;
> the WS `fill` channel is the execution source of truth.

## GET /portfolio/orders/{id}
`{ "order": <Order> }`. Poll after an IOC to reach a terminal `status`
(`executed` | `canceled`).

## DELETE /portfolio/orders/{id}
`{ "order": <Order>, "reduced_by_fp": "1.00" }`. Kalshi **reduces** the order;
`reduced_by_fp` is how many contracts were cancelled. `<= 0` means it had already
filled.
