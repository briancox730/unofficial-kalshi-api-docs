"""RSA-PSS request signing for the Kalshi trading API.

Kalshi authenticates every REST call AND the WebSocket upgrade with three headers:

    KALSHI-ACCESS-KEY        your API key id
    KALSHI-ACCESS-TIMESTAMP  current Unix time in MILLISECONDS
    KALSHI-ACCESS-SIGNATURE  base64( RSA-PSS-SHA256( f"{ts_ms}{METHOD}{PATH}" ) )

Gotchas baked in here (see docs/authentication.md and docs/gotchas.md):
  * the timestamp is MILLISECONDS, not seconds
  * the signed PATH excludes the query string — everything from "?" on is dropped
    (the request URL still keeps the query; only the signature drops it)
  * PSS uses SHA-256 for both the hash and the MGF1 mask, with salt length 32
  * your PEM may be PKCS#8 ("BEGIN PRIVATE KEY") or PKCS#1 ("BEGIN RSA PRIVATE
    KEY"); cryptography's load_pem_private_key handles both
"""
import base64
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key


def load_private_key(pem):
    """Parse a Kalshi RSA private key from PEM text (PKCS#8 or PKCS#1)."""
    if isinstance(pem, str):
        pem = pem.encode()
    return load_pem_private_key(pem, password=None)


def sign(private_key, timestamp_ms, method, path):
    """Return the base64 KALSHI-ACCESS-SIGNATURE for one request.

    The signed message is ``f"{timestamp_ms}{METHOD}{PATH}"`` with PATH stripped
    of its query string. PSS is randomized, so the signature differs on every
    call even for identical inputs.
    """
    path_no_query = path.split("?", 1)[0]
    message = f"{timestamp_ms}{method}{path_no_query}".encode()
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode()


def auth_headers(api_key, private_key, method, path):
    """Build the three Kalshi auth headers for a single request."""
    ts_ms = int(time.time() * 1000)
    return {
        "KALSHI-ACCESS-KEY": api_key,
        "KALSHI-ACCESS-SIGNATURE": sign(private_key, ts_ms, method, path),
        "KALSHI-ACCESS-TIMESTAMP": str(ts_ms),
    }
