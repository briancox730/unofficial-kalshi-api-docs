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
| GET | `/portfolio/fills` | your executions (authoritative) |
| POST | `/portfolio/events/orders` | place an order (**V2** — see below) |
| DELETE | `/portfolio/events/orders/{id}` | cancel (reduce) an order (**V2**) |
| GET | `/portfolio/orders/{id}` | poll an order (**no V2 equivalent published** — see below) |

> **⚠ v1 order endpoints were sunset on 2026-06-18.** `POST /portfolio/orders`
> and `DELETE /portfolio/orders/{id}` now return
> `410 {"code":"deprecated_v1_order_endpoint"}`. Use the V2 `/portfolio/events/orders`
> paths. The V2 wire format is **YES-referenced** and the response shape changed —
> see the [POST](#post-portfolioeventsorders-v2) section and
> [gotchas.md](gotchas.md) #1. Read endpoints (markets, orderbook, positions,
> balance, fills) are unchanged.

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

## GET /portfolio/fills
Your executions — the **authoritative** record of what filled and the fees paid,
and the recommended way to detect fills on resting orders (the V2 order API
dropped the single-order GET). Query params: `ticker`, `order_id`, `limit`,
`cursor`. Returns `{ "fills": [...], "cursor": "" }`. Each fill carries `count`, a
YES-referenced price, `side`, `is_taker`, fees, and `created_time`. **Unaffected**
by the v1→v2 order migration.

## POST /portfolio/events/orders  (V2)

> The legacy `POST /portfolio/orders` was **sunset 2026-06-18** (`410`,
> `deprecated_v1_order_endpoint`). This is the replacement. The client's
> `place_order(side, action, …)` keeps the old intent vocabulary and translates
> it to this body for you (`kalshi.to_v2_order_body`).

V2 is **YES-referenced**: there is no `action`, no `side: yes|no`, and no
`yes_price`/`no_price`. The body carries one `side` ∈ {`bid`, `ask`} and one
`price` — the **YES** limit price as a 4-decimal dollar string.

```jsonc
{
  "ticker": "…",
  "side": "bid" | "ask",               // bid BUYS yes, ask SELLS yes
  "count": "1.00",                      // fixed-point STRING, not an int
  "price": "0.5000",                    // YES-referenced, 4-decimal dollar string
  "self_trade_prevention_type": "taker_at_cross",  // REQUIRED ("maker" is the other value)
  "time_in_force": "immediate_or_cancel" | "good_till_canceled" | "fill_or_kill",
  "client_order_id": "uuid",           // optional idempotency key
  "post_only": true                    // optional: reject if it would take liquidity
}
```

**Mapping your intent → `side` + `price`** (`bid` iff `is_buy == is_yes`; a NO
order maps onto the YES book as `1 − price`):

| intent | V2 `side` | V2 `price` |
|---|---|---|
| buy YES 50¢  | `bid` | `0.5000` |
| sell YES 85¢ | `ask` | `0.8500` |
| buy NO 30¢   | `ask` | `0.7000`  (1 − 0.30) |
| sell NO 30¢  | `bid` | `0.7000` |

Compute the price in integer **ten-thousandths** (1¢ = 100) so the `1 − p` NO flip
and sub-cent "deci-cent" ticks stay exact — e.g. NO `0.9980` → `0.0020`, never
`0.0020000001`. The client does this for you.

**Response is flat** — no `order` wrapper, no `status`, and none of the v1 `_fp`
or `taker_fill_cost_dollars` fields:

```jsonc
{
  "order_id": "…",
  "client_order_id": "…",
  "fill_count": "1.00",
  "remaining_count": "0.00",
  "average_fill_price": "0.9300",   // YES-referenced VWAP; present only if fill > 0
  "average_fee_paid": "0.0200",     // PER-CONTRACT, not total
  "ts_ms": 1715793600123
}
```

Derive the things the v1 `Order` used to give you (the client's
`normalize_order_response` does all of this):

- **`status`** — synthesize it: `remaining_count == 0` → `executed` if any fill
  else `canceled`; otherwise `resting` under GTC, `canceled` under IOC/FOK.
- **Your realized $/contract** — `average_fill_price` is YES-referenced, so it's
  your price directly for a YES order and `1 − average_fill_price` for a NO order
  (one rule for buys *and* sells; it already encodes the old v1 complement).
- **Total fees** — `average_fee_paid × fill_count` (the field is per-contract).

> Gotchas: to **close**, sell the side you hold (Kalshi doesn't net YES/NO
> intraday — see gotchas #2). IOC can fill even against an empty-looking book;
> the WS `fill` channel / `GET /portfolio/fills` are the execution source of truth.

## GET /portfolio/orders/{id}
Kalshi has **not published a V2 single-order GET**. The v1 path *may* still
resolve V2-created order IDs (returning `{ "order": <Order> }`), but this is
**unverified** — confirm against demo before relying on it. For terminal status of
an IOC, the create response is already terminal (synthesize `status` from
`fill_count`/`remaining_count`). For **resting** orders, detect fills via
`GET /portfolio/fills` or the WS `fill` channel instead of polling here.

## DELETE /portfolio/events/orders/{id}  (V2)
Flat response — no `order` wrapper, no `status`:

```jsonc
{ "order_id": "…", "reduced_by": "1.00", "ts_ms": 1715793660456 }
```

Kalshi **reduces** rather than deletes; `reduced_by` is how many contracts were
actually cancelled. `reduced_by <= 0` (`"0.00"`) means the order had **already
filled** — you cancelled nothing (don't then try to "undo" the fill). The client
returns `{ order_id, reduced_count, status, raw }` with
`status = "canceled"` when `reduced_count > 0`.
