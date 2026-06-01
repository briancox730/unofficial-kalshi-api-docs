# Kalshi API gotchas

The behaviours that aren't in the official docs and cost people time (and money)
to discover. Each is **what → why → the fix**. Verified against the live API in
2026; Kalshi can change any of this, so re-check against the demo environment.

---

### 1. A "sell" is reported on the *opposite* side

`action=sell, side=yes` reduces your YES position, but the fill comes back with
`outcome_side=no` and `taker_fill_cost_dollars` set to the **NO-side complement**.

**Fix:** your realized proceeds per contract are `1 - taker_fill_cost/fill_count`,
not the response's `yes_price`. (`kalshi.sell_proceeds()` does this.)

```
# sold YES at ~5c -> response: outcome_side="no", taker_fill_cost="0.948"
proceeds = 1 - 0.948 / 1 = 0.052   # ~5.2c
```

### 2. The `*_price_dollars` sell trap (this one costs money)

A **sell** priced via `yes_price_dollars` / `no_price_dollars` at the exact bid
can get booked by the matching engine as an **opposite-side BUY** — i.e. it
*hedges* instead of *flattening*. You think you closed; you actually now hold
both sides.

**Fix:** to close, use **integer** `yes_price` / `no_price` cents at a low floor
(e.g. a few cents below the bid). The IOC still fills at the best bid ≥ your
floor. See `examples/08_sell_to_close.py`.

### 3. You can hold BOTH yes and no at the same time

Kalshi does **not** net your YES and NO contracts intraday. Buying the opposite
side does **not** flatten — you accumulate both lots and they only net at
settlement (each $1 winner pays, the loser expires worthless).

**Fix:** to flatten, **sell the side you hold**. Don't "close" a YES by buying NO.

### 4. `positions()` lags fills by ~1 second

Right after an order fills, `GET /portfolio/positions` can still return the
**pre-order** (stale) state. Reading it once immediately after trading lies to you.

**Fix:** poll until it reflects your order (see `poll_net()` in
`examples/08_sell_to_close.py`).

### 5. `last_updated_ts` is an ISO string, not an epoch int

In a `market_position`, `last_updated_ts` looks like
`"2026-05-31T23:34:49.912729Z"`. If your model/struct types it as an integer,
the **entire positions response fails to parse** — but only when you actually
hold a position (an empty list parses fine, so it hides in testing).

**Fix:** treat it as a string.

### 6. The orderbook is BIDS ONLY

`GET /markets/{ticker}/orderbook` returns only bids on each side. There is no
"ask" field. The ask on one side is the **complement of the best bid on the
other**:

```
yes_ask = 100 - best_no_bid
no_ask  = 100 - best_yes_bid     # cents
```

### 7. `?status=open` has a ~30s boundary lag (and `active` is invalid)

Right after a market settles, the list endpoint can still return the
just-settled market **first**. A naive `markets[0]` picks a dead market.

**Fix:** filter client-side by parsing `close_time` and taking the soonest
*future* close (see `examples/02_list_markets.py`). Also: valid `status` values
are `open`, `closed`, `settled` — `active` is rejected as an invalid filter.

### 8. Two price encodings: integer cents vs sub-cent dollars

- `yes_price` / `no_price`: **integer cents**, 1–99. Use for normal ticks.
- `yes_price_dollars` / `no_price_dollars`: **fixed-point dollar strings** (e.g.
  `"0.9980"`), for sub-cent precision. Kalshi quotes 0.001 "deci-cent" ticks in
  the 0.90–1.00 band.

They are **mutually exclusive per side** — send one or the other, never both.

### 9. Fixed-point `_fp` fields are strings, and `position_fp` is signed

`fill_count_fp`, `remaining_count_fp`, `initial_count_fp`, `position_fp`,
`reduced_by_fp`, etc. are **stringly-typed decimals** (`"1.00"`). Parse to float.
`position_fp` is **signed**: positive = YES contracts, negative = NO, 0 = flat.

### 10. Cancel "reduces", it doesn't delete

`DELETE /portfolio/orders/{id}` returns the order with remaining count zeroed and
a `reduced_by_fp` telling you how many contracts were actually cancelled. If
`reduced_by_fp <= 0`, the order had **already filled** — you didn't cancel
anything (don't then also try to "undo" the fill).

### 11. WebSocket deltas are fractional — accumulate them exactly

`orderbook_delta` ships **fractional** size changes (e.g. `74.77`, `"-300.00"`).
If you round each delta independently, you leave phantom ±residual levels that
keep dead price levels alive and can fake a crossed book.

**Fix:** accumulate sizes as exact floats; remove a level only when it nets to
~0 (use an epsilon like `1e-6`). See `kalshi/orderbook.py`.

### 12. WebSocket price/size fields are polymorphic

`price_dollars`, `delta_fp`, and snapshot row values arrive **sometimes as JSON
numbers, sometimes as strings** (`0.62` vs `"0.62"`). Parse defensively
(`float(value)` handles both).

### 13. IOC orders fill even when the REST top-of-book looks empty

The REST orderbook snapshot can show an empty book while resting liquidity exists
— an aggressive IOC still fills. Also, the `POST /orders` response can return
**before** the execution is reflected; the WebSocket `fill` channel is the
source of truth for what actually executed.

### 14. Timestamps for signing are milliseconds

`KALSHI-ACCESS-TIMESTAMP` and the value you sign are **Unix milliseconds**, not
seconds. Off-by-1000 here gives you `401`s.

### 15. Sign the path WITHOUT the query string

The signed message is `f"{ts_ms}{METHOD}{PATH}"` where `PATH` is everything
**before** the `?`. The request URL keeps the query; only the signature drops it.

### 16. Two orderbook envelope shapes

The REST orderbook may come back as `{"orderbook": {"yes": [...], "no": [...]}}`
or as a bare `{"yes": [...], "no": [...]}`. Handle both
(`body.get("orderbook", body)`).

### 17. Taker fee (empirical)

Observed taker fee per contract at price `P` (dollars):
`ceil(0.07 * P * (1 - P) * 100) / 100`. Maker fills are free. This is empirical —
**confirm against Kalshi's current fee schedule** before relying on it.
