"""Auth tests: the RSA-PSS signature must verify, and the signed message must be
exactly `{ts}{METHOD}{PATH-without-query}` — the two things people get wrong.
"""
import base64

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from kalshi.auth import auth_headers, load_private_key, sign


def _verify(public_key, b64_sig, message):
    public_key.verify(
        base64.b64decode(b64_sig),
        message.encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
        hashes.SHA256(),
    )


def test_pkcs8_pem_loads(pkcs8_pem):
    assert load_private_key(pkcs8_pem) is not None


def test_pkcs1_pem_loads(pkcs1_pem):
    assert load_private_key(pkcs1_pem) is not None


def test_load_accepts_bytes(pkcs8_pem):
    assert load_private_key(pkcs8_pem.encode()) is not None


def test_signature_verifies_against_public_key(rsa_key, pkcs8_pem):
    key = load_private_key(pkcs8_pem)
    ts = 1717200000000
    sig = sign(key, ts, "GET", "/trade-api/v2/portfolio/balance")
    _verify(rsa_key.public_key(), sig, f"{ts}GET/trade-api/v2/portfolio/balance")


def test_query_string_is_stripped_from_signed_message(rsa_key, pkcs8_pem):
    key = load_private_key(pkcs8_pem)
    ts = 1717200000000
    sig = sign(key, ts, "GET", "/trade-api/v2/markets?status=open&limit=1")
    # verifies against the path WITHOUT the query ...
    _verify(rsa_key.public_key(), sig, f"{ts}GET/trade-api/v2/markets")
    # ... and NOT against the path WITH the query (that's the gotcha).
    with pytest.raises(InvalidSignature):
        _verify(rsa_key.public_key(), sig, f"{ts}GET/trade-api/v2/markets?status=open&limit=1")


def test_pss_signature_is_randomized(pkcs8_pem):
    key = load_private_key(pkcs8_pem)
    assert sign(key, 1, "GET", "/x") != sign(key, 1, "GET", "/x")


def test_method_and_timestamp_change_the_signed_message(rsa_key, pkcs8_pem):
    key = load_private_key(pkcs8_pem)
    get_sig = sign(key, 5, "GET", "/x")
    # a GET signature must not verify as a POST over the same path/ts
    with pytest.raises(InvalidSignature):
        _verify(rsa_key.public_key(), get_sig, "5POST/x")


def test_auth_headers_shape_and_ms_timestamp(pkcs8_pem):
    key = load_private_key(pkcs8_pem)
    headers = auth_headers("mykey", key, "GET", "/x?y=1")
    assert set(headers) == {
        "KALSHI-ACCESS-KEY",
        "KALSHI-ACCESS-SIGNATURE",
        "KALSHI-ACCESS-TIMESTAMP",
    }
    assert headers["KALSHI-ACCESS-KEY"] == "mykey"
    # timestamp is a millisecond integer (13 digits this century)
    ts = headers["KALSHI-ACCESS-TIMESTAMP"]
    assert ts.isdigit() and len(ts) >= 13
