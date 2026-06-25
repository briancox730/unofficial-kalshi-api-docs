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

#: `self_trade_prevention_type` — REQUIRED in V2. "taker_at_cross" cancels the
#: incoming taker portion on a self-cross (the conservative choice). The only
#: other documented value is "maker". Used as the default in `place_order` /
#: `to_v2_order_body`; defined here so it's in scope for those signatures.
STP_TAKER_AT_CROSS = "taker_at_cross"


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

    # --- order endpoints (Kalshi V2 — see docs/gotchas.md #1) --------------
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
        self_trade_prevention_type=STP_TAKER_AT_CROSS,
    ):
        """POST /portfolio/events/orders  (Kalshi **V2** create endpoint).

        Kalshi sunset the v1 `POST /portfolio/orders` on 2026-06-18 — it now
        returns `410 {"code":"deprecated_v1_order_endpoint"}`. The V2 book is
        **YES-referenced**: the wire body carries one `side` in {bid, ask} and a
        single YES-referenced `price` — there is no `action`/`yes_price`/`no_price`.

        This method keeps the familiar intent vocabulary and translates it to the
        V2 wire format (see `to_v2_order_body`). The flat V2 response is normalized
        back to a stable dict (see `normalize_order_response`).

        side   : "yes" | "no"   (which contract you intend to trade)
        action : "buy" | "sell"
        count  : whole contracts (int)

        Price: integer cents via `yes_price`/`no_price` (1-99), OR sub-cent dollars
        via `yes_price_dollars`/`no_price_dollars` ("0.9980"). Mutually exclusive
        per side. Translated to a single YES-referenced 4-decimal dollar string with
        exact integer (ten-thousandths) math, so the NO-side `1 - p` flip and the
        deci-cent ticks never drift.

        For a RESTING order pass `time_in_force="good_till_canceled"` explicitly
        (don't rely on omission). `self_trade_prevention_type` is **required** in V2
        ("taker_at_cross" is the conservative default).

        Returns a normalized dict: `order_id`, `client_order_id`, `status`
        (synthesized — V2 omits it), `fill_count`, `remaining_count`, `fill_price`
        (YOUR side's realized $/contract, None if unfilled), `fees` (total), `raw`
        (the flat V2 body).
        """
        body = to_v2_order_body(
            ticker, side, action, count,
            time_in_force=time_in_force,
            post_only=post_only,
            yes_price=yes_price,
            no_price=no_price,
            yes_price_dollars=yes_price_dollars,
            no_price_dollars=no_price_dollars,
            client_order_id=client_order_id or str(uuid.uuid4()),
            self_trade_prevention_type=self_trade_prevention_type,
        )
        resp = self._request("POST", f"{API_PREFIX}/portfolio/events/orders", body)
        return normalize_order_response(side, action, time_in_force, resp)

    def get_order(self, order_id):
        """GET /portfolio/orders/{id} -> {order}.

        Kalshi has **not published a V2 single-order GET**. The v1 path *may* still
        resolve V2-created order IDs, but this is unverified — confirm against demo
        before relying on it for live fill detection. The authoritative, unaffected
        sources are `fills()` (GET /portfolio/fills) and the private WebSocket
        `fill` channel. See docs/gotchas.md #1.
        """
        return self.get(f"{API_PREFIX}/portfolio/orders/{order_id}")

    def fills(self, ticker=None, order_id=None, limit=None, cursor=None):
        """GET /portfolio/fills — your executions (UNAFFECTED by the v2 migration).

        The authoritative record of what actually executed and the fees paid, and
        the recommended way to detect fills on resting orders. Optional filters:
        `ticker`, `order_id`. Returns `{fills: [...], cursor}` (cursor empty = last
        page). Each fill carries `count`, a YES-referenced price, side, and fees.
        """
        params = []
        if ticker:
            params.append(f"ticker={ticker}")
        if order_id:
            params.append(f"order_id={order_id}")
        if limit:
            params.append(f"limit={limit}")
        if cursor:
            params.append(f"cursor={cursor}")
        q = "&".join(params)
        return self.get(f"{API_PREFIX}/portfolio/fills" + (f"?{q}" if q else ""))

    def cancel_order(self, order_id):
        """DELETE /portfolio/events/orders/{id}  (Kalshi **V2** cancel).

        V2 returns a flat `{order_id, reduced_by, ts_ms}` — no `order` wrapper, no
        `status`. Kalshi REDUCES rather than deletes; `reduced_by` is how many
        contracts were actually cancelled. Returns a normalized dict: `order_id`,
        `reduced_count` (float), `status` (synthesized), `raw`. `reduced_count <= 0`
        means the order had already filled — you cancelled nothing.
        """
        resp = self._request("DELETE", f"{API_PREFIX}/portfolio/events/orders/{order_id}")
        reduced = fp(resp.get("reduced_by"))
        return {
            "order_id": resp.get("order_id"),
            "reduced_count": reduced,
            "status": "canceled" if reduced > 0 else "unchanged",
            "raw": resp,
        }


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


# --- Kalshi V2 order translation (the YES-referenced wire format) -----------
# V2 is YES-REFERENCED. There is no action / side(yes|no) / yes_price / no_price
# on the wire: one `side` in {bid, ask} and one `price` (the YES limit price).
# `bid` buys YES, `ask` sells YES; a NO order maps onto the YES book:
#     buy NO @ n  ==  ask @ (1 - n)        sell NO @ n  ==  bid @ (1 - n)
# Closed form: send `bid` iff (action == "buy") == (side == "yes").
# (STP_TAKER_AT_CROSS is defined at the top of the module — it's the required
# `self_trade_prevention_type` default.)


def _side_price_ttth(side, yes_price, no_price, yes_price_dollars, no_price_dollars):
    """OUR side's limit price in ten-thousandths of a dollar (1c = 100). None if unset.

    Whole-cent (`yes_price`/`no_price`) takes precedence over the sub-cent dollar
    string (`*_price_dollars`). Integer ten-thousandths keep the `1 - p` NO flip and
    the deci-cent ticks exact — no float drift (this is real money).
    """
    if side == "yes":
        if yes_price is not None:
            return int(yes_price) * 100
        if yes_price_dollars is not None:
            return round(float(yes_price_dollars) * 10_000)
    elif side == "no":
        if no_price is not None:
            return int(no_price) * 100
        if no_price_dollars is not None:
            return round(float(no_price_dollars) * 10_000)
    else:
        raise ValueError(f"side must be 'yes' or 'no', got {side!r}")
    return None


def to_v2_order_body(
    ticker,
    side,
    action,
    count,
    *,
    time_in_force="immediate_or_cancel",
    post_only=None,
    yes_price=None,
    no_price=None,
    yes_price_dollars=None,
    no_price_dollars=None,
    client_order_id=None,
    self_trade_prevention_type=STP_TAKER_AT_CROSS,
):
    """Translate intent (side/action/price) into Kalshi's V2 create body.

    Returns the exact JSON dict POSTed to `/portfolio/events/orders`. Raises
    ValueError if no price is set for the chosen side or the resulting
    YES-referenced price falls outside (0, 1).
    """
    if action not in ("buy", "sell"):
        raise ValueError(f"action must be 'buy' or 'sell', got {action!r}")
    is_bid = (action == "buy") == (side == "yes")
    side_ttth = _side_price_ttth(
        side, yes_price, no_price, yes_price_dollars, no_price_dollars
    )
    if side_ttth is None:
        raise ValueError(f"no price set for {side!r} side")
    yes_ttth = side_ttth if side == "yes" else 10_000 - side_ttth
    if not (1 <= yes_ttth <= 9_999):
        raise ValueError(f"YES-referenced price {yes_ttth}/10000 out of (0, 1)")
    body = {
        "ticker": ticker,
        "side": "bid" if is_bid else "ask",
        "count": f"{int(count)}.00",                # V2 wants a fixed-point STRING
        "price": f"0.{yes_ttth:04d}",               # yes_ttth in [1,9999] -> "0.NNNN"
        "self_trade_prevention_type": self_trade_prevention_type,  # REQUIRED in V2
    }
    if time_in_force is not None:
        body["time_in_force"] = time_in_force
    if post_only:
        body["post_only"] = True
    if client_order_id:
        body["client_order_id"] = client_order_id
    return body


def our_fill_price(side, resp):
    """OUR side's realized $/contract from a V2 order response (None if unfilled).

    `average_fill_price` is YES-referenced; our price is it directly for a YES
    order and its complement for a NO order. ONE rule for both buys and sells —
    it already encodes the old v1 `1 - taker_fill_cost/fill_count` arithmetic.
    """
    avg = resp.get("average_fill_price")
    if avg is None:
        return None
    yes = float(avg)
    return yes if side == "yes" else 1.0 - yes


def synth_status(resp, time_in_force):
    """Synthesize an order `status` (V2 omits it) from fill/remaining + TIF.

    Returns "executed" | "canceled" | "resting". A remainder is only `resting`
    under GTC-equivalent TIF; IOC/FOK cancel whatever didn't fill immediately.
    """
    fill = fp(resp.get("fill_count"))
    rem = fp(resp.get("remaining_count"))
    if rem == 0:
        return "executed" if fill > 0 else "canceled"
    if time_in_force in (None, "good_till_canceled"):
        return "resting"
    return "canceled"


def normalize_order_response(side, action, time_in_force, resp):
    """Fold a flat V2 create response into a stable, documented dict.

    Keys: `order_id`, `client_order_id`, `status`, `fill_count`,
    `remaining_count`, `fill_price` (our side's realized $/ct, None if unfilled),
    `fees` (total $ = average_fee_paid x fill_count), `raw` (the flat V2 body).
    """
    fill_count = fp(resp.get("fill_count"))
    price = our_fill_price(side, resp)
    if price is not None:
        assert 0.0 <= price <= 1.0, f"fill_price out of range: {price}"
    per_ct_fee = resp.get("average_fee_paid")
    fees = float(per_ct_fee) * fill_count if per_ct_fee is not None else 0.0
    return {
        "order_id": resp.get("order_id"),
        "client_order_id": resp.get("client_order_id"),
        "status": synth_status(resp, time_in_force),
        "fill_count": fill_count,
        "remaining_count": fp(resp.get("remaining_count")),
        "fill_price": price,
        "fees": fees,
        "raw": resp,
    }
