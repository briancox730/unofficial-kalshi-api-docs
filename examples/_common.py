"""Shared helpers for the example scripts: load .env, build a client, confirm prod.

Importing this also puts the repo root on sys.path so `import kalshi` works when
you run `python examples/xx.py` from the repo root.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from kalshi import KalshiHttpClient  # noqa: E402  (after sys.path tweak)


def load_env(path=None):
    """Minimal .env loader (no dependency). KEY=VALUE lines; # comments ignored.

    Real environment variables take precedence over .env (setdefault).
    """
    path = path or os.path.join(_ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def client_from_env():
    load_env()
    return KalshiHttpClient.from_env()


def require_confirm(args, action_desc):
    """Guard real orders. Refuses to send without --confirm; warns loudly on prod."""
    env = os.environ.get("KALSHI_ENV", "demo")
    print(f"\n  >> {action_desc}")
    print(f"  >> environment: {env.upper()}" + ("  (REAL money!)" if env == "prod" else ""))
    if not getattr(args, "confirm", False):
        print("  >> dry run — add --confirm to actually send. Nothing was sent.\n")
        return False
    return True
