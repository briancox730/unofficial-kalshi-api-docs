# Authentication

Kalshi signs every REST call and the WebSocket upgrade with an **RSA private
key** (RSA-PSS). You get an API key id and a `.pem` private key from your account
settings (demo and production are separate accounts/keys).

## The three headers

Every authenticated request carries:

| Header | Value |
|---|---|
| `KALSHI-ACCESS-KEY` | your API key id |
| `KALSHI-ACCESS-TIMESTAMP` | current Unix time in **milliseconds** |
| `KALSHI-ACCESS-SIGNATURE` | base64( RSA-PSS-SHA256( message ) ) |

The signed **message** is the concatenation:

```
{timestamp_ms}{HTTP_METHOD}{PATH}
```

where:

- `timestamp_ms` — the same millisecond value you put in the timestamp header
- `HTTP_METHOD` — `GET`, `POST`, or `DELETE`
- `PATH` — the request path **without the query string** (everything before `?`).
  The request URL still includes the query; only the signature drops it.

Example message: `1717200000000GET/trade-api/v2/portfolio/balance`

## The signature

- Algorithm: **RSA-PSS**
- Hash: **SHA-256**
- MGF: **MGF1 with SHA-256**
- Salt length: **32 bytes** (the digest size)
- Output: base64 (standard alphabet)

PSS is randomized, so the signature is different on every call — that's expected.

## Python

```python
import base64, time
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

key = load_pem_private_key(open("kalshi.pem", "rb").read(), password=None)

def headers(api_key, method, path):
    ts = str(int(time.time() * 1000))                      # milliseconds
    msg = f"{ts}{method}{path.split('?')[0]}".encode()     # path WITHOUT query
    sig = key.sign(
        msg,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY": api_key,
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
    }
```

`cryptography`'s `load_pem_private_key` reads **both** PEM formats Kalshi may hand
you: PKCS#8 (`-----BEGIN PRIVATE KEY-----`) and PKCS#1
(`-----BEGIN RSA PRIVATE KEY-----`). No special handling needed.

## Credentials & environments

This repo reads:

- `KALSHI_API_KEY` — the key id
- `KALSHI_PEM_CONTENTS` (inline PEM) **or** `KALSHI_PEM_PATH` (file, default `./kalshi.pem`)
- `KALSHI_ENV` — `demo` (default) or `prod`

Base URLs:

| Env | REST | WebSocket |
|---|---|---|
| demo | `https://demo-api.kalshi.co` | `wss://demo-api.kalshi.co/trade-api/ws/v2` |
| prod | `https://api.elections.kalshi.com` | `wss://api.elections.kalshi.com/trade-api/ws/v2` |

**Demo and production credentials are not interchangeable.** Start on demo.

## Common 401 causes

- timestamp in **seconds** instead of milliseconds
- signing the path **with** the query string
- signing the full URL instead of just the path
- clock skew (your machine's time is off)
- using a demo key against production (or vice versa)
