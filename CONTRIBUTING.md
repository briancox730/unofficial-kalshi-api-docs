# Contributing

Thanks for helping keep this reference accurate. The whole point of the project
is that it documents how the Kalshi API *actually* behaves — so the most valuable
contributions are corrections and newly discovered quirks, backed by evidence.

Not affiliated with Kalshi. This documents *how the API works*, not what to
trade — please keep contributions market-agnostic and strategy-free.

## Reporting or fixing a gotcha

The gotchas live in [`docs/gotchas.md`](docs/gotchas.md). Each entry follows the
same shape: **what → why → the fix**. When you add one (or correct one):

- **What** — the surprising behaviour, stated concretely (the exact status code,
  field name, or response shape).
- **Why** — the underlying reason, if you know it. If you don't, say so rather
  than guessing.
- **The fix** — what to do instead, ideally with a one-line code snippet.
- **How you verified it** — see below. Note the environment (demo vs prod) and
  roughly when you checked.

Small correction? Open a PR straight against `docs/gotchas.md`. Not sure it's
real, or can't verify it yourself? Open an issue describing what you saw and how
to reproduce it, and someone can confirm before it goes in the docs.

## Verifying against the live API

API-behaviour claims in this repo are only as good as the last time someone
checked them, and Kalshi can change the API at any time. Before you assert a new
behaviour:

1. Reproduce it against **demo** ([demo.kalshi.co](https://demo.kalshi.co)) —
   demo credentials are separate from production. Use `KALSHI_ENV=demo`.
2. Capture the concrete evidence: the request path/body you sent and the raw
   response (status code + JSON). Redact your API key.
3. If it only reproduces on **prod**, say so explicitly in the entry — some
   behaviour differs between environments, and that difference is itself useful.

`examples/01_auth_and_balance.py` is the quickest end-to-end check that your
signing works; the other `examples/` scripts default to demo and are handy for
poking at real responses.

**Never commit credentials.** Your `.env` and `*.pem` are gitignored — keep them
that way, and scrub keys/tokens out of any pasted responses.

## Offline tests are required

The test suite in [`tests/`](tests/) must stay **fully offline**: it generates a
throwaway RSA key and never hits the network or needs real credentials. This is
what lets CI run on every PR without secrets.

If your change touches code in `kalshi/`:

```bash
pip install -e ".[dev]"   # installs pytest
pytest -q                 # must be green
```

- Add or update tests for the behaviour you changed.
- Do **not** introduce a test that requires network access or credentials. If a
  behaviour genuinely can't be checked offline, gate it behind a marker (e.g.
  `@pytest.mark.live`) so the default `pytest` run — and CI — stays green, and
  mention it in the PR.

CI runs `pytest` on Python 3.11 and 3.12; the package targets Python 3.9+.

## Pull requests

Keep PRs focused — one gotcha or one fix per PR where you can. Describe what you
observed and how you verified it in the PR body. That's it. Thanks again.
