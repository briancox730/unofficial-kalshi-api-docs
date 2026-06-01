"""List open markets (any series). Demonstrates the close_time sort that avoids
the ~30s '?status=open' boundary lag: just after a market settles, the API can
still list it first, so sort by soonest-FUTURE close_time instead of taking [0].

    python examples/02_list_markets.py [--series KXSERIES] [--limit 10]
"""
import argparse
from datetime import datetime, timezone

from _common import client_from_env


def parse_close(market):
    ct = market.get("close_time")
    return datetime.fromisoformat(ct.replace("Z", "+00:00")) if ct else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", default=None, help="optional series_ticker filter")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    client = client_from_env()
    page = client.markets(series_ticker=args.series, status="open", limit=args.limit)
    markets = page.get("markets", [])

    now = datetime.now(timezone.utc)
    future = sorted((m for m in markets if (parse_close(m) or now) > now),
                    key=lambda m: parse_close(m) or now)

    print(f"{len(markets)} open markets returned; soonest-future first:")
    for m in future[: args.limit]:
        print(f"  {m['ticker']:34s} yes_ask={m.get('yes_ask')} "
              f"no_ask={m.get('no_ask')} closes={m.get('close_time')}")
    if page.get("cursor"):
        print(f"next page cursor: {page['cursor']}")


if __name__ == "__main__":
    main()
