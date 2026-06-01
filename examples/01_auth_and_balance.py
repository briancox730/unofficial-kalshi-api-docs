"""Confirm auth works end-to-end: sign a request and read your balance.

If this prints a balance, your signing is correct. Run:

    python examples/01_auth_and_balance.py
"""
from _common import client_from_env


def main():
    client = client_from_env()
    print(f"env: {client.env} -> {client.base_url}")
    print("exchange status:", client.exchange_status())
    bal = client.balance()
    print(f"balance: ${bal.get('balance', 0) / 100:.2f}"
          f"   payout reserve: ${bal.get('payout', 0) / 100:.2f}")


if __name__ == "__main__":
    main()
