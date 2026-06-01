"""How to actually CLOSE (flatten) a Kalshi position — the #1 gotcha, demonstrated.

Why this is tricky:
  * A "sell" is filled on the COMPLEMENT side (sell yes -> reported on the no
    side at 1 - price). Realized proceeds = 1 - taker_fill_cost/fill_count.
  * Kalshi does NOT net yes vs no intraday — buying the opposite side does not
    flatten; you'd hold BOTH lots until settlement.
  * Therefore, to flatten you must SELL the side you hold, with INTEGER cents at
    a low floor (the IOC still fills at the best bid >= floor). A sell priced via
    *_price_dollars at the exact bid can get booked as an opposite-side BUY that
    HEDGES instead of reducing.

This demo buys 1 contract, then sells-to-close, printing the net position
before/after (it should end at 0). Demo by default; refuses prod unless
KALSHI_ENV=prod; needs --confirm.

    python examples/08_sell_to_close.py TICKER [--side yes] [--buy-price 60] [--confirm]
"""
import argparse
import time

from _common import client_from_env, require_confirm
from kalshi import position_contracts, sell_proceeds


def net_for(client, ticker):
    for p in client.positions(ticker=ticker).get("market_positions", []):
        if p.get("ticker") == ticker:
            return position_contracts(p)
    return 0.0


def poll_net(client, ticker, tries=8, delay=0.3):
    """positions() lags ~1s — poll instead of reading once."""
    net = 0.0
    for _ in range(tries):
        net = net_for(client, ticker)
        time.sleep(delay)
    return net


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--side", default="yes", choices=["yes", "no"])
    ap.add_argument("--buy-price", type=int, default=60, help="buy cap in cents (fills at the ask)")
    ap.add_argument("--floor", type=int, default=5, help="sell floor in cents (fills at the best bid)")
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args()

    client = client_from_env()
    if not require_confirm(args, f"buy 1 {args.side} then sell-to-close on {args.ticker}"):
        return

    pf = "yes_price" if args.side == "yes" else "no_price"

    # 1) open a position
    client.place_order(args.ticker, side=args.side, action="buy", count=1, **{pf: args.buy_price})
    print("after buy:   net =", poll_net(client, args.ticker))

    # 2) close it: SELL the side we hold, integer cents, low floor.
    resp = client.place_order(args.ticker, side=args.side, action="sell", count=1, **{pf: args.floor})
    order = resp.get("order", resp)
    proceeds = sell_proceeds(order)
    print(f"sell proceeds ~ ${proceeds:.3f}/contract" if proceeds is not None else "sell: no fill")
    print("after close: net =", poll_net(client, args.ticker), " (0 == flattened correctly)")


if __name__ == "__main__":
    main()
