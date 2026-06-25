# Kalshi API gotchas

The behaviours that aren't in the official docs and cost people time (and money)
to discover. Each is **what → why → the fix**. Verified against the live API in
2026; Kalshi can change any of this, so re-check against the demo environment.

---

### 1. The v1 order endpoint is gone (410) — V2 is YES-referenced

**This is a breaking change.** Kalshi **sunset `POST /portfolio/orders` on
2026-06-18**; it now returns `410 {"code":"deprecated_v1_order_endpoint"}`. The
replacement is **`POST /portfolio/events/orders`**, and the wire format is
completely different. (`DELETE /portfolio/orders/{id}` was likewise replaced by
`DELETE /portfolio/events/orders/{id}`.)

The client hides all of this — `place_order(side, action, price…)` still speaks
the old intent vocabulary and translates it (`kalshi.to_v2_order_body` /
`normalize_order_response`). But if you build the request yourself, here is what
changed:

**a) The book is YES-referenced.** There is no `action`, no `side: yes|no`, no
`yes_price`/`no_price`. The body carries one **`side` ∈ {`bid`, `ask`}** (`bid`
buys YES, `ask` sells YES) and one **`price`** — the YES limit price as a
4-decimal dollar string. A NO order maps onto the YES book:

```
buy NO @ n   ==  ask @ (1 − n)        sell NO @ n   ==  bid @ (1 − n)
```

Closed form: send `bid` iff `is_buy == is_yes`.

| your intent  | V2 `side` | V2 `price` |
|---|---|---|
| buy YES 50¢  | `bid` | `0.5000` |
| sell YES 85¢ | `ask` | `0.8500` |
| buy NO 30¢   | `ask` | `0.7000`  (1 − 0.30) |
| sell NO 30¢  | `bid` | `0.7000` |

Compute the price in **integer ten-thousandths** (1¢ = 100) so the `1 − p` NO flip
and sub-cent "deci-cent" ticks stay exact (real money — no float drift): NO
`0.9980` → `0.0020`, never `0.00199999`.

**b) New / changed request fields.**

- `self_trade_prevention_type` is now **required** — use `"taker_at_cross"`
  (cancels the incoming taker portion on a self-cross; the conservative default).
  The other documented value is `"maker"`.
- `count` is a **fixed-point string** (`"1.00"`), not an int.
- `time_in_force` vocabulary is unchanged (`immediate_or_cancel` |
  `good_till_canceled` | `fill_or_kill`) but **send it explicitly for resting
  orders** — pass `good_till_canceled` rather than relying on omission, so resting
  semantics can't silently change.

**c) The response is flat — and your realized price is YES-referenced.** No
`order` wrapper, no `status`, and **none** of the v1 `*_fp` count fields or
`taker_fill_cost_dollars`:

```jsonc
{ "order_id": "…", "client_order_id": "…",
  "fill_count": "1.00", "remaining_count": "0.00",
  "average_fill_price": "0.9300",   // YES-referenced VWAP; present only if fill > 0
  "average_fee_paid": "0.0200",     // PER-CONTRACT, not total
  "ts_ms": 1715793600123 }
```

Derive what v1 used to hand you:

- **`status`** (omitted): `remaining_count == 0` → `executed` if any fill else
  `canceled`; otherwise `resting` under GTC, `canceled` under IOC/FOK.
- **Your realized $/contract**: `average_fill_price` is YES-referenced, so it's
  your price directly for a YES order and `1 − average_fill_price` for a NO order.
  This is **one rule for buys *and* sells** — it already encodes the old v1
  "a sell is reported on the complement side, proceeds = `1 − cost/fill`"
  arithmetic, so you no longer special-case sells. (`kalshi.our_fill_price`.)
- **Total fees**: `average_fee_paid × fill_count` (the field is per-contract).

**d) Cancel returns flat too.** `DELETE /portfolio/events/orders/{id}` →
`{ "order_id", "reduced_by": "1.00", "ts_ms" }`. Kalshi **reduces** rather than
deletes; `reduced_by` is how many contracts were cancelled. `reduced_by <= 0`
(`"0.00"`) means the order had **already filled** — you cancelled nothing.

**e) There is no published V2 single-order GET.** `GET /portfolio/orders/{id}`
*may* still resolve V2 order IDs, but it's unverified — don't rely on it for live
fill detection. An IOC's create response is already terminal; for **resting**
orders, detect fills via **`GET /portfolio/fills`** (authoritative, unaffected) or
the WebSocket `fill` channel.

### 2. To close a position, *sell the side you hold* (Kalshi doesn't net intraday)

Kalshi tracks YES and NO lots **separately** and only nets them **at
settlement**. Buying the opposite side does **not** flatten — you accumulate both
lots and hold both until settlement (each $1 winner pays, the loser expires
worthless). So "close my YES by buying NO" **hedges, it doesn't flatten**.

**Fix:** to flatten, **sell the side you hold**, with **integer cents** at a low
floor (a few cents below the bid). The IOC still fills at the best bid ≥ your
floor. See `examples/08_sell_to_close.py`.

> Historical note: under the v1 API a sell priced via `*_price_dollars` at the
> exact bid could get booked as an opposite-side **buy** that hedged instead of
> reducing. V2 removes that ambiguity — the order carries an explicit `bid`/`ask`
> side — but selling the held side at a low integer floor is still the robust way
> to close.

### 3. `positions()` lags fills by ~1 second

Right after an order fills, `GET /portfolio/positions` can still return the
**pre-order** (stale) state. Reading it once immediately after trading lies to you.

**Fix:** poll until it reflects your order (see `poll_net()` in
`examples/08_sell_to_close.py`).

### 4. `last_updated_ts` is an ISO string, not an epoch int

In a `market_position`, `last_updated_ts` looks like
`"2026-05-31T23:34:49.912729Z"`. If your model/struct types it as an integer,
the **entire positions response fails to parse** — but only when you actually
hold a position (an empty list parses fine, so it hides in testing).

**Fix:** treat it as a string.

### 5. The orderbook is BIDS ONLY

`GET /markets/{ticker}/orderbook` returns only bids on each side. There is no
"ask" field. The ask on one side is the **complement of the best bid on the
other**:

```
yes_ask = 100 - best_no_bid
no_ask  = 100 - best_yes_bid     # cents
```

### 6. `?status=open` has a ~30s boundary lag (and `active` is invalid)

Right after a market settles, the list endpoint can still return the
just-settled market **first**. A naive `markets[0]` picks a dead market.

**Fix:** filter client-side by parsing `close_time` and taking the soonest
*future* close (see `examples/02_list_markets.py`). Also: valid `status` values
are `open`, `closed`, `settled` — `active` is rejected as an invalid filter.

### 7. Two price encodings: integer cents vs sub-cent dollars

- `yes_price` / `no_price`: **integer cents**, 1–99. Use for normal ticks.
- `yes_price_dollars` / `no_price_dollars`: **fixed-point dollar strings** (e.g.
  `"0.9980"`), for sub-cent precision. Kalshi quotes 0.001 "deci-cent" ticks in
  the 0.90–1.00 band.

They are **mutually exclusive per side** — send one or the other, never both. The
client accepts either and translates both to the single YES-referenced V2 `price`
(see #1) using exact integer math, so deci-cent precision survives the NO flip.

### 8. Fixed-point `_fp` fields are strings, and `position_fp` is signed

`position_fp`, `reduced_by_fp`, the WebSocket `count_fp`/`delta_fp`, etc. are
**stringly-typed decimals** (`"1.00"`). Parse to float. `position_fp` is
**signed**: positive = YES contracts, negative = NO, 0 = flat.

> Note: the **V2 order create/cancel** responses use the *un*-suffixed
> `fill_count` / `remaining_count` / `reduced_by` (still decimal strings) — the
> `_fp` suffix lives on the positions and WebSocket payloads, not the V2 order
> body. Parse all of them the same way (`kalshi.fp`).

### 9. WebSocket deltas are fractional — accumulate them exactly

`orderbook_delta` ships **fractional** size changes (e.g. `74.77`, `"-300.00"`).
If you round each delta independently, you leave phantom ±residual levels that
keep dead price levels alive and can fake a crossed book.

**Fix:** accumulate sizes as exact floats; remove a level only when it nets to
~0 (use an epsilon like `1e-6`). See `kalshi/orderbook.py`.

### 10. WebSocket price/size fields are polymorphic

`price_dollars`, `delta_fp`, and snapshot row values arrive **sometimes as JSON
numbers, sometimes as strings** (`0.62` vs `"0.62"`). Parse defensively
(`float(value)` handles both).

### 11. IOC orders fill even when the REST top-of-book looks empty

The REST orderbook snapshot can show an empty book while resting liquidity exists
— an aggressive IOC still fills. Also, the order create response can return
**before** the execution is reflected; the WebSocket `fill` channel (and
`GET /portfolio/fills`) is the source of truth for what actually executed.

### 12. Timestamps for signing are milliseconds

`KALSHI-ACCESS-TIMESTAMP` and the value you sign are **Unix milliseconds**, not
seconds. Off-by-1000 here gives you `401`s.

### 13. Sign the path WITHOUT the query string

The signed message is `f"{ts_ms}{METHOD}{PATH}"` where `PATH` is everything
**before** the `?`. The request URL keeps the query; only the signature drops it.

### 14. Two orderbook envelope shapes

The REST orderbook may come back as `{"orderbook": {"yes": [...], "no": [...]}}`
or as a bare `{"yes": [...], "no": [...]}`. Handle both
(`body.get("orderbook", body)`).

### 15. Taker fee (empirical)

Observed taker fee per contract at price `P` (dollars):
`ceil(0.07 * P * (1 - P) * 100) / 100`. Maker fills are free. This is empirical —
**confirm against Kalshi's current fee schedule** before relying on it. Under V2
the order response also reports `average_fee_paid` **per contract** (multiply by
`fill_count` for the total).
