# unofficial-kalshi-api-docs

The practical, **unofficial** reference for the [Kalshi](https://kalshi.com)
trading API — the auth scheme, the REST endpoints, the WebSocket protocol, and
(most usefully) the **undocumented behaviours** that cost people time and money to
discover. Plain Python: a small reusable client plus runnable, copy-paste examples.

> Not affiliated with Kalshi. Market-agnostic — this documents *how the API works*,
> not what to trade. No trading strategy here, by design.

## The stuff that isn't in the official docs → [`docs/gotchas.md`](docs/gotchas.md)

A few that will bite you:

- **A "sell" is reported on the opposite side.** `sell yes` comes back as
  `outcome_side=no`; your proceeds are `1 - taker_fill_cost/fill_count`.
- **To close a position, *sell the side you hold*.** Kalshi doesn't net YES/NO
  intraday — buying the opposite side **hedges, it doesn't flatten** (you end up
  holding both until settlement). And a sell priced via `*_price_dollars` at the
  bid can get booked as an opposite-side buy — use **integer cents**.
- **The orderbook is bids-only** — `yes_ask = 100 - best_no_bid`.
- **`positions()` lags fills by ~1s** and returns stale state — poll it.
- **`last_updated_ts` is an ISO string, not an int** (breaks naive parsers only
  when you actually hold a position).
- **Sign the path *without* the query string**, with a **millisecond** timestamp.
- **WebSocket deltas are fractional** — accumulate exactly or you get phantom
  book levels.

Full list with the *why* and the *fix*: **[`docs/gotchas.md`](docs/gotchas.md)**.

## Quickstart

```bash
pip install -r requirements.txt
cp .env.example .env        # then fill in your DEMO key + pem; KALSHI_ENV=demo
python examples/01_auth_and_balance.py
```

If that prints your balance, your signing is correct. Get demo credentials at
[demo.kalshi.co](https://demo.kalshi.co) (separate from production).

Prefer one self-contained file? [`quickstart_no_deps.py`](quickstart_no_deps.py)
does auth + balance + a live orderbook frame in ~50 lines with no local imports.

## Using the client

```python
from kalshi import KalshiHttpClient
client = KalshiHttpClient.from_env()        # reads KALSHI_API_KEY / KALSHI_PEM_* / KALSHI_ENV

print(client.balance())
print(client.markets(status="open", limit=5))
print(client.orderbook("SOME-TICKER"))
print(client.positions())
```

## Layout

```
kalshi/            reusable client (importable)
  auth.py            RSA-PSS signing + headers
  client.py          signed REST helpers, one per endpoint
  orderbook.py       snapshot+delta book reconstruction (bids-only, exact accumulation)
  ws.py              async WebSocket client (orderbook + fills)
examples/          runnable recipes (import the client)
  01_auth_and_balance.py     07_stream_fills_ws.py
  02_list_markets.py         08_sell_to_close.py   <- the "how to actually close" demo
  03_get_orderbook.py
  04_place_and_cancel_order.py
  05_positions_and_pnl.py
  06_stream_orderbook_ws.py
quickstart_no_deps.py        one self-contained file
docs/
  gotchas.md         <- start here
  authentication.md  rest-endpoints.md  websocket.md  glossary.md
```

## Examples

All default to **demo**. The ones that place real orders
(`04_place_and_cancel_order.py`, `08_sell_to_close.py`) require `--confirm` and
refuse production unless you set `KALSHI_ENV=prod` deliberately.

```bash
python examples/02_list_markets.py --limit 5
python examples/03_get_orderbook.py SOME-TICKER
python examples/06_stream_orderbook_ws.py SOME-TICKER
python examples/04_place_and_cancel_order.py SOME-TICKER --price 5 --confirm   # demo
python examples/08_sell_to_close.py SOME-TICKER --confirm                       # demo
```

## Install as a package

```bash
pip install -e .          # editable install; `import kalshi` works anywhere
# or build a wheel:  python -m build   (then pip install dist/*.whl)
```

The importable package is `kalshi`. The examples and docs are repo content, not
part of the installed distribution.

## Development & tests

The tests are offline — they generate a throwaway RSA key and never hit the
network or need real credentials. They cover the two things people get wrong
(the RSA-PSS signature and stripping the query from the signed path) plus the
orderbook reconstruction and the client's path/body building.

```bash
pip install -e ".[dev]"   # installs pytest
pytest                    # runs tests/ (configured via pyproject.toml)
```

## Safety & disclaimer

- **Demo by default.** Production trades real money — opt in explicitly.
- Your `.env` and `.pem` are gitignored. **Never commit credentials.**
- This is **unofficial** and provided **as-is, without warranty** (MIT). Behaviour
  was verified against the live API in 2026; Kalshi can change it any time — when
  in doubt, check against demo. You are responsible for anything you run with real
  money.

## Contributing

Found another quirk, or something changed? PRs welcome — add it to
[`docs/gotchas.md`](docs/gotchas.md) with a short *what / why / fix* and, ideally,
how you verified it.
