"""In-memory Kalshi orderbook from a WebSocket snapshot + deltas.

Two quirks this handles (see docs/gotchas.md):

  * Kalshi only sends BIDS. The ask on one side is the complement of the best
    bid on the other:  yes_ask = $1 - best_no_bid,  no_ask = $1 - best_yes_bid.

  * Deltas carry FRACTIONAL sizes (e.g. 74.77, or "-300.00"). Accumulate them
    EXACTLY; never round per-delta or you leave phantom residual levels that
    fake a crossed book. A level is dropped when its size nets to ~0.

Prices are kept in "mills" (integer thousandths of a dollar, price * 1000) so
Kalshi's 0.001 deci-cent ticks stay exact. WebSocket prices are in DOLLARS
(the `*_dollars_fp` / `price_dollars` fields).
"""
SIZE_EPSILON = 1e-6
MILLS_PER_DOLLAR = 1000


def to_mills(price):
    """Dollar price (str like "0.62" or number 0.62) -> integer mills."""
    return round(float(price) * MILLS_PER_DOLLAR)


class OrderBook:
    """One market's two bid books, fed by `orderbook_snapshot` + `orderbook_delta`."""

    def __init__(self, ticker=None):
        self.ticker = ticker
        self.yes_bids = {}  # mills -> size (float, accumulated exactly)
        self.no_bids = {}

    def _book(self, side):
        return self.yes_bids if side == "yes" else self.no_bids

    def apply_snapshot(self, yes_levels=None, no_levels=None):
        """Replace the book from a snapshot. Levels are [price_dollars, size] pairs."""
        self.yes_bids.clear()
        self.no_bids.clear()
        for price, size in yes_levels or []:
            self.yes_bids[to_mills(price)] = float(size)
        for price, size in no_levels or []:
            self.no_bids[to_mills(price)] = float(size)

    def apply_delta(self, side, price, delta):
        """Apply one delta. `delta` is a CHANGE in size (can be negative)."""
        book = self._book(side)
        m = to_mills(price)
        book[m] = book.get(m, 0.0) + float(delta)
        if book[m] <= SIZE_EPSILON:
            book.pop(m, None)

    # --- reads -------------------------------------------------------------
    def best_yes_bid(self):
        return max(self.yes_bids) / MILLS_PER_DOLLAR if self.yes_bids else None

    def best_no_bid(self):
        return max(self.no_bids) / MILLS_PER_DOLLAR if self.no_bids else None

    def yes_ask(self):
        nb = self.best_no_bid()
        return None if nb is None else round(1.0 - nb, 4)

    def no_ask(self):
        yb = self.best_yes_bid()
        return None if yb is None else round(1.0 - yb, 4)

    def top(self):
        """Best bid/ask for both sides, as a dict of dollar prices (or None)."""
        return {
            "yes_bid": self.best_yes_bid(),
            "yes_ask": self.yes_ask(),
            "no_bid": self.best_no_bid(),
            "no_ask": self.no_ask(),
        }
