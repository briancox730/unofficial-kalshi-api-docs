"""Fetch a market's REST orderbook and DERIVE the asks.

Kalshi's orderbook is BIDS ONLY. Each side is [[price_cents, count], ...] with
the best (highest) bid first. The ask on one side is the complement of the best
bid on the OTHER side:  yes_ask = 100 - best_no_bid.

    python examples/03_get_orderbook.py TICKER
"""
import argparse

from _common import client_from_env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    args = ap.parse_args()

    client = client_from_env()
    # Kalshi may wrap as {"orderbook": {...}} or return a bare body; handle both.
    body = client.orderbook(args.ticker)
    ob = body.get("orderbook", body) or {}
    yes = ob.get("yes") or []
    no = ob.get("no") or []

    print(f"market: {args.ticker}")
    print(f"  yes bids (top 3): {yes[:3]}")
    print(f"  no  bids (top 3): {no[:3]}")
    if no:
        print(f"  derived yes_ask = 100 - {no[0][0]} = {100 - no[0][0]}c")
    if yes:
        print(f"  derived no_ask  = 100 - {yes[0][0]} = {100 - yes[0][0]}c")
    if not yes and not no:
        print("  (empty book — this market currently has no resting bids)")


if __name__ == "__main__":
    main()
