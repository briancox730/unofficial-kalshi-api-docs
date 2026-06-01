"""Self-contained Kalshi quickstart — copy this ONE file and run it.

No local imports. Just:

    pip install requests cryptography websockets
    export KALSHI_API_KEY=...  KALSHI_PEM_PATH=./kalshi.pem  KALSHI_ENV=demo
    python quickstart_no_deps.py

It signs a request, prints your balance, then prints a few live orderbook frames.
Everything you need to talk to Kalshi in ~50 lines.
"""
import asyncio
import base64
import json
import os
import time

import requests
import websockets
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

API_KEY = os.environ["KALSHI_API_KEY"]
PEM = os.environ.get("KALSHI_PEM_CONTENTS") or open(
    os.environ.get("KALSHI_PEM_PATH", "./kalshi.pem")).read()
ENV = os.environ.get("KALSHI_ENV", "demo")
REST = {"demo": "https://demo-api.kalshi.co",
        "prod": "https://api.elections.kalshi.com"}[ENV]
WS = {"demo": "wss://demo-api.kalshi.co/trade-api/ws/v2",
      "prod": "wss://api.elections.kalshi.com/trade-api/ws/v2"}[ENV]
KEY = load_pem_private_key(PEM.encode(), password=None)


def headers(method, path):
    ts = str(int(time.time() * 1000))                       # milliseconds!
    msg = f"{ts}{method}{path.split('?')[0]}".encode()      # sign path WITHOUT query
    sig = KEY.sign(msg,
                   padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
                   hashes.SHA256())
    return {"KALSHI-ACCESS-KEY": API_KEY,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode()}


def get(path):
    r = requests.get(REST + path, headers=headers("GET", path))
    r.raise_for_status()
    return r.json()


async def stream_one_book():
    markets = get("/trade-api/v2/markets?status=open&limit=1").get("markets", [])
    if not markets:
        print("no open markets right now")
        return
    ticker = markets[0]["ticker"]
    print("subscribing to", ticker)
    hdrs = headers("GET", "/trade-api/ws/v2")
    try:
        ws = await websockets.connect(WS, additional_headers=hdrs)   # websockets >= 13
    except TypeError:
        ws = await websockets.connect(WS, extra_headers=hdrs)        # older websockets
    async with ws:
        await ws.send(json.dumps({"id": 1, "cmd": "subscribe",
                                  "params": {"channels": ["orderbook_delta"],
                                             "market_tickers": [ticker]}}))
        for _ in range(5):
            print("ws:", await ws.recv())


if __name__ == "__main__":
    print("env:", ENV)
    print("balance: $%.2f" % (get("/trade-api/v2/portfolio/balance")["balance"] / 100))
    asyncio.run(stream_one_book())
