# Glossary

Just enough vocabulary to read the rest of the docs. Market-agnostic — applies to
any Kalshi market.

- **Contract** — a binary claim that settles to **$1 if true, $0 if false**.
  Every market has a **YES** contract and a **NO** contract.
- **YES / NO** — the two sides of a market. Buying YES at price `p` costs `p` and
  pays `$1` if the market resolves yes. Buying NO costs `1 - p_yes` and pays `$1`
  if it resolves no.
- **Price** — quoted in cents (1–99) or dollars (0.01–0.99). YES and NO prices are
  complements: `yes_price + no_price = $1` (≈, modulo the spread).
- **Bid / ask** — Kalshi's book holds **bids only**; the ask for one side is the
  complement of the best bid on the other (`yes_ask = 100 - best_no_bid`).
- **Position netting** — Kalshi tracks YES and NO lots separately and only nets
  them **at settlement**. You can hold both at once. To flatten, sell the side you
  hold (don't buy the opposite).
- **`position_fp`** — your signed net position: **+ = YES contracts, − = NO**.
- **`_fp` fields** — "fixed-point" values delivered as **strings** (`"1.00"`);
  parse to float. Examples: `fill_count_fp`, `delta_fp`, `position_fp`,
  `reduced_by_fp`.
- **Deci-cent / mills** — Kalshi quotes 0.001-dollar ("deci-cent") ticks in the
  0.90–1.00 band. "Mills" = price × 1000 (integer), used to keep ticks exact.
- **Taker / maker** — a **taker** order crosses the book and executes immediately
  (and pays the fee); a **maker** order rests on the book (free if it fills as a
  maker). `post_only=true` forces maker-only (reject if it would take).
- **Time in force** — `immediate_or_cancel` (IOC: fill what you can now, cancel
  the rest), `fill_or_kill` (FOK: all-or-nothing now), `good_till_canceled` (GTC:
  rest until filled or cancelled).
- **`seq`** — per-WebSocket-connection sequence number; a gap means a dropped
  frame.
- **`sid`** — subscription id returned in a `subscribed` frame; used to modify a
  subscription.
- **Series / event / market** — a **series** (e.g. a recurring question) contains
  **events**, which contain individual **markets** (the things you trade, each with
  a `ticker`).
