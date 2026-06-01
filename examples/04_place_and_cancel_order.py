"""Place a small resting limit order, then cancel it.

Shows order placement and that DELETE "reduces" rather than deletes: the response
carries `reduced_by_fp` (how many contracts were cancelled; <= 0 means it had
already filled). Uses a low non-marketable buy so it rests, then cancels it.

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
    resp = client.place_order(
        args.ticker, side=args.side, action="buy", count=1,
        time_in_force="good_till_canceled", **{price_field: args.price},
    )
    order = resp.get("order", resp)
    order_id = order.get("order_id")
    print(f"placed: id={order_id} status={order.get('status')}")

    time.sleep(0.5)
    cancel = client.cancel_order(order_id)
    print(f"cancel: reduced_by_fp={cancel.get('reduced_by_fp')} "
          f"(<= 0 would mean the order had already filled)")


if __name__ == "__main__":
    main()
