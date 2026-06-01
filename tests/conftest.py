"""Shared pytest fixtures: throwaway RSA keys (no real credentials needed)."""
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture(scope="session")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def pkcs8_pem(rsa_key):
    """PEM in PKCS#8 form: -----BEGIN PRIVATE KEY-----"""
    return rsa_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


@pytest.fixture(scope="session")
def pkcs1_pem(rsa_key):
    """PEM in PKCS#1 (traditional) form: -----BEGIN RSA PRIVATE KEY-----"""
    return rsa_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
