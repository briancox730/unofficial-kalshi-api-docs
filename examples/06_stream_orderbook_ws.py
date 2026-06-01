"""Stream a live orderbook over WebSocket (snapshot + deltas) and print top-of-book.

Demonstrates the WS subscribe handshake, fractional-delta accumulation, and the
bids-only -> derived-ask convention (all handled in kalshi/orderbook.py).

    python examples/06_stream_orderbook_ws.py TICKER [TICKER2 ...]
"""
import argparse
import asyncio
import os

from _common import load_env
from kalshi import load_private_key, stream_orderbook


async def run(tickers):
    load_env()
    api_key = os.environ["KALSHI_API_KEY"]
    pem = os.environ.get("KALSHI_PEM_CONTENTS") or open(
        os.environ.get("KALSHI_PEM_PATH", "./kalshi.pem")).read()
    env = os.environ.get("KALSHI_ENV", "demo")
    key = load_private_key(pem)

    print(f"streaming {tickers} on {env} ... Ctrl-C to stop")
    async for ticker, book in stream_orderbook(api_key, key, tickers, env=env):
        t = book.top()
        print(f"{ticker}  yes_bid={t['yes_bid']} yes_ask={t['yes_ask']}  "
              f"no_bid={t['no_bid']} no_ask={t['no_ask']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="+")
    args = ap.parse_args()
    try:
        asyncio.run(run(args.tickers))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
