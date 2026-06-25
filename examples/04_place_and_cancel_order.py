"""Place a small resting limit order, then cancel it.

Shows the Kalshi **V2** order path (the v1 `POST /portfolio/orders` was sunset
2026-06-18 — see docs/gotchas.md #1). `place_order` translates side/action/price
into the YES-referenced V2 body and normalizes the flat response. DELETE
"reduces" rather than deletes: the result carries `reduced_count` (how many
contracts were cancelled; <= 0 means it had already filled). Uses a low
non-marketable GTC buy so it rests, then cancels it.

Demo by default. Refuses prod unless KALSHI_ENV=prod. Needs --confirm to send.

    python examples/04_place_and_cancel_order.py TICKER [--side yes] [--price 5] [--confirm]
"""
import argparse
import time

from _common import client_from_env, require_confirm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--side", default="yes", choices=["yes", "no"])
    ap.add_argument("--price", type=int, default=5, help="limit price in cents (1-99)")
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args()

    client = client_from_env()
    if not require_confirm(args, f"place + cancel a 1-contract {args.side} buy @ {args.price}c"):
        return

    price_field = "yes_price" if args.side == "yes" else "no_price"
    # GTC so the (non-marketable) order rests instead of cancelling immediately.
    order = client.place_order(
        args.ticker, side=args.side, action="buy", count=1,
        time_in_force="good_till_canceled", **{price_field: args.price},
    )
    order_id = order["order_id"]
    print(f"placed: id={order_id} status={order['status']} "
          f"(status is synthesized — V2 omits it)")

    time.sleep(0.5)
    cancel = client.cancel_order(order_id)
    print(f"cancel: reduced_count={cancel['reduced_count']} status={cancel['status']} "
          f"(<= 0 would mean the order had already filled)")


if __name__ == "__main__":
    main()
