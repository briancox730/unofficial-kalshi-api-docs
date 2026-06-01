"""A thin, signed Kalshi REST client — one method per endpoint, no trading logic.

Market-agnostic: works for any Kalshi market or series. Defaults to the demo
environment. See docs/rest-endpoints.md for the full field reference and
docs/gotchas.md for the behaviours that bite people.
"""
import os
import uuid

import requests

from .auth import auth_headers, load_private_key

BASE_URLS = {
    "prod": "https://api.elections.kalshi.com",
    "demo": "https://demo-api.kalshi.co",
}
API_PREFIX = "/trade-api/v2"


class KalshiError(RuntimeError):
    """Raised on a non-2xx response; the message carries the status + body."""


class KalshiHttpClient:
    def __init__(self, api_key, private_key, env="demo", session=None):
        if env not in BASE_URLS:
            raise ValueError(f"env must be one of {list(BASE_URLS)}, got {env!r}")
        self.api_key = api_key
        self.private_key = private_key
        self.env = env
        self.base_url = BASE_URLS[env]
        self.session = session or requests.Session()

    @classmethod
    def from_env(cls):
        """Build a client from KALSHI_API_KEY, KALSHI_PEM_* and KALSHI_ENV."""
        api_key = os.environ.get("KALSHI_API_KEY")
        if not api_key:
            raise KalshiError("KALSHI_API_KEY is not set (see .env.example)")
        pem = os.environ.get("KALSHI_PEM_CONTENTS")
        if not pem:
            path = os.environ.get("KALSHI_PEM_PATH", "./kalshi.pem")
            with open(path) as fh:
                pem = fh.read()
        env = os.environ.get("KALSHI_ENV", "demo")
        return cls(api_key, load_private_key(pem), env=env)

    # --- core request ------------------------------------------------------
    def _request(self, method, path, body=None):
        # The signature drops the query string (handled in auth.sign); the URL
        # keeps it. Pass the full path (with ?query) here.
        headers = auth_headers(self.api_key, self.private_key, method, path)
        headers["Content-Type"] = "application/json"
        resp = self.session.request(method, self.base_url + path, headers=headers, json=body)
        if not resp.ok:
            raise KalshiError(f"{resp.status_code} {method} {path}: {resp.text[:400]}")
        return resp.json() if resp.content else {}

    def get(self, path):
        return self._request("GET", path)

    # --- read endpoints ----------------------------------------------------
    def exchange_status(self):
        """GET /exchange/status -> {exchange_active, trading_active}."""
        return self.get(f"{API_PREFIX}/exchange/status")

    def balance(self):
        """GET /portfolio/balance -> {balance, payout} (cents)."""
        return self.get(f"{API_PREFIX}/portfolio/balance")

    def markets(self, series_ticker=None, status="open", limit=None, cursor=None):
        """GET /markets. status must be open|closed|settled (NOT 'active').

        Returns {markets: [...], cursor}. cursor is empty when there are no more
        pages. See docs/gotchas.md for the ~30s status-filter lag at boundaries.
        """
        params = []
        if limit:
            params.append(f"limit={limit}")
        if series_ticker:
            params.append(f"series_ticker={series_ticker}")
        if status:
            params.append(f"status={status}")
        if cursor:
            params.append(f"cursor={cursor}")
        q = "&".join(params)
        return self.get(f"{API_PREFIX}/markets" + (f"?{q}" if q else ""))

    def market(self, ticker):
        """GET /markets/{ticker} -> a single market."""
        return self.get(f"{API_PREFIX}/markets/{ticker}")

    def orderbook(self, ticker):
        """GET /markets/{ticker}/orderbook.

        BIDS ONLY. Each side is [[price_cents, count], ...]; asks are the
        complement (yes_ask = 100 - best_no_bid). See docs/gotchas.md.
        """
        return self.get(f"{API_PREFIX}/markets/{ticker}/orderbook")

    def positions(self, ticker=None):
        """GET /portfolio/positions (count_filter=position drops flat rows).

        Returns {market_positions: [...], event_positions, cursor}. Each
        position has a signed `position_fp` (+ = yes, - = no). NOTE: this
        endpoint lags fills by ~1s — poll it, don't read once. See gotchas.
        """
        path = f"{API_PREFIX}/portfolio/positions?count_filter=position"
        if ticker:
            path += f"&ticker={ticker}"
        return self.get(path)

    # --- order endpoints ---------------------------------------------------
    def place_order(
        self,
        ticker,
        side,
        action,
        count,
        *,
        yes_price=None,
        no_price=None,
        yes_price_dollars=None,
        no_price_dollars=None,
        time_in_force="immediate_or_cancel",
        client_order_id=None,
        post_only=None,
    ):
        """POST /portfolio/orders.

        side   : "yes" | "no"   (which contract)
        action : "buy" | "sell"
        count  : whole contracts (int)

        Price: pass integer cents via `yes_price`/`no_price` (1-99), OR sub-cent
        dollars via `yes_price_dollars`/`no_price_dollars` (e.g. "0.9980"). They
        are mutually exclusive per side.

        IMPORTANT (see docs/gotchas.md): to CLOSE a position, sell the side you
        hold with INTEGER cents at a low floor. A sell priced via *_price_dollars
        at the exact bid can get booked as an opposite-side buy that hedges
        instead of flattening.
        """
        body = {
            "ticker": ticker,
            "side": side,
            "action": action,
            "count": count,
            "time_in_force": time_in_force,
            "client_order_id": client_order_id or str(uuid.uuid4()),
        }
        for key, val in (
            ("yes_price", yes_price),
            ("no_price", no_price),
            ("yes_price_dollars", yes_price_dollars),
            ("no_price_dollars", no_price_dollars),
            ("post_only", post_only),
        ):
            if val is not None:
                body[key] = val
        return self._request("POST", f"{API_PREFIX}/portfolio/orders", body)

    def get_order(self, order_id):
        """GET /portfolio/orders/{id} -> {order}. Poll this for terminal status."""
        return self.get(f"{API_PREFIX}/portfolio/orders/{order_id}")

    def cancel_order(self, order_id):
        """DELETE /portfolio/orders/{id}.

        Kalshi REDUCES rather than deletes; `reduced_by_fp` tells you how many
        contracts were cancelled. reduced_by_fp <= 0 means it had already filled.
        """
        return self._request("DELETE", f"{API_PREFIX}/portfolio/orders/{order_id}")


# --- small parse helpers for Kalshi's stringly-typed fixed-point fields -----
def fp(value, default=0.0):
    """Parse a Kalshi `_fp` / `_dollars` field (string or number) to float."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def position_contracts(market_position):
    """Signed net contracts from a market_position: + = yes, - = no, 0 = flat."""
    return fp(market_position.get("position_fp"))


def sell_proceeds(order):
    """Realized $/contract for a SELL.

    Kalshi reports a sell on the COMPLEMENT side, so `taker_fill_cost_dollars`
    is the opposite-side cost; proceeds = 1 - cost/filled. Do not read the
    response's own yes/no_price as your sale price.
    """
    filled = fp(order.get("fill_count_fp"))
    cost = fp(order.get("taker_fill_cost_dollars"))
    if filled <= 0:
        return None
    return max(0.0, min(1.0, 1.0 - cost / filled))
