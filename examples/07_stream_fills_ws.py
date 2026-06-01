"""Stream your order executions over the private WebSocket `fill` channel.

Each fill reports side, action, both prices, count_fp, is_taker, and the signed
post_position_fp (your position AFTER the fill). The fill channel is the source
of truth for executions — a POST /orders response can return before the fill.

    python examples/07_stream_fills_ws.py
"""
import asyncio
import os

from _common import load_env
from kalshi import KalshiWsClient, load_private_key


async def run():
    load_env()
    api_key = os.environ["KALSHI_API_KEY"]
    pem = os.environ.get("KALSHI_PEM_CONTENTS") or open(
        os.environ.get("KALSHI_PEM_PATH", "./kalshi.pem")).read()
    env = os.environ.get("KALSHI_ENV", "demo")

    async with KalshiWsClient(api_key, load_private_key(pem), env=env) as client:
        await client.subscribe(["fill"])
        print(f"listening for fills on {env} ... Ctrl-C to stop")
        async for frame in client.messages():
            if frame.get("type") == "fill":
                m = frame["msg"]
                print(f"FILL {m.get('market_ticker')} {m.get('action')} {m.get('side')} "
                      f"count={m.get('count_fp')} taker={m.get('is_taker')} "
                      f"post_position={m.get('post_position_fp')}")
            elif frame.get("type") == "error":
                print("error:", frame.get("msg"))


def main():
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
