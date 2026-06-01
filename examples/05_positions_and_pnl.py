"""Read your open positions and decode the signed position_fp.

`position_fp` is a signed fixed-point string: positive = YES contracts,
negative = NO contracts, 0 = flat. NOTE: this endpoint lags fills by ~1s, so if
you just traded, poll it rather than reading once.

    python examples/05_positions_and_pnl.py [--ticker TICKER]
"""
import argparse

from _common import client_from_env
from kalshi import fp, position_contracts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default=None)
    args = ap.parse_args()

    client = client_from_env()
    page = client.positions(ticker=args.ticker)
    positions = page.get("market_positions", [])
    if not positions:
        print("flat — no open positions.")
        print("(if you JUST traded, positions() lags ~1s — poll a few times.)")
        return

    for p in positions:
        net = position_contracts(p)
        side = "YES" if net > 0 else "NO" if net < 0 else "flat"
        print(f"  {p['ticker']:34s} net={net:+g} ({side})  "
              f"exposure=${fp(p.get('market_exposure_dollars')):.2f}  "
              f"realized=${fp(p.get('realized_pnl_dollars')):.2f}  "
              f"fees=${fp(p.get('fees_paid_dollars')):.2f}")


if __name__ == "__main__":
    main()
