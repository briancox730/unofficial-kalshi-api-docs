"""Client tests: URL/path/body building (no network) + the fixed-point helpers."""
import pytest

from kalshi.auth import load_private_key
from kalshi.client import (
    BASE_URLS,
    KalshiError,
    KalshiHttpClient,
    fp,
    position_contracts,
    sell_proceeds,
)


@pytest.fixture
def client(pkcs8_pem):
    """A client whose `_request` is stubbed to capture what would be sent."""
    c = KalshiHttpClient("k", load_private_key(pkcs8_pem), env="demo")
    captured = {}

    def fake_request(method, path, body=None):
        captured.update(method=method, path=path, body=body)
        return {"ok": True}

    c._request = fake_request
    c.captured = captured
    return c


def test_base_url_by_env(pkcs8_pem):
    key = load_private_key(pkcs8_pem)
    assert KalshiHttpClient("k", key, env="demo").base_url == BASE_URLS["demo"]
    assert KalshiHttpClient("k", key, env="prod").base_url == BASE_URLS["prod"]


def test_invalid_env_raises(pkcs8_pem):
    with pytest.raises(ValueError):
        KalshiHttpClient("k", load_private_key(pkcs8_pem), env="bogus")


def test_markets_builds_query(client):
    client.markets(series_ticker="KXFOO", status="open", limit=3)
    assert client.captured["path"] == "/trade-api/v2/markets?limit=3&series_ticker=KXFOO&status=open"


def test_markets_without_params(client):
    client.markets(status=None)
    assert client.captured["path"] == "/trade-api/v2/markets"


def test_positions_always_filters_and_optional_ticker(client):
    client.positions()
    assert client.captured["path"] == "/trade-api/v2/portfolio/positions?count_filter=position"
    client.positions(ticker="ABC")
    assert client.captured["path"].endswith("&ticker=ABC")


def test_place_order_body(client):
    client.place_order("ABC", "yes", "sell", 1, yes_price=5, client_order_id="cid")
    assert client.captured["method"] == "POST"
    assert client.captured["path"] == "/trade-api/v2/portfolio/orders"
    assert client.captured["body"] == {
        "ticker": "ABC", "side": "yes", "action": "sell", "count": 1,
        "time_in_force": "immediate_or_cancel", "client_order_id": "cid", "yes_price": 5,
    }


def test_place_order_autogenerates_client_order_id(client):
    client.place_order("ABC", "no", "buy", 2, no_price=40)
    assert client.captured["body"]["client_order_id"]
    # unset price fields are omitted, not sent as null
    assert "yes_price" not in client.captured["body"]
    assert "post_only" not in client.captured["body"]


def test_cancel_uses_delete(client):
    client.cancel_order("oid")
    assert client.captured["method"] == "DELETE"
    assert client.captured["path"] == "/trade-api/v2/portfolio/orders/oid"


def test_from_env_requires_api_key(monkeypatch):
    monkeypatch.delenv("KALSHI_API_KEY", raising=False)
    with pytest.raises(KalshiError):
        KalshiHttpClient.from_env()


# --- fixed-point parse helpers ---
def test_fp_parses_strings_numbers_and_garbage():
    assert fp("1.50") == 1.5
    assert fp(2) == 2.0
    assert fp(None) == 0.0
    assert fp("garbage") == 0.0


def test_position_contracts_is_signed():
    assert position_contracts({"position_fp": "3.00"}) == 3.0   # yes
    assert position_contracts({"position_fp": "-2.00"}) == -2.0  # no
    assert position_contracts({}) == 0.0                          # flat


def test_sell_proceeds_uses_the_complement():
    # sold 1; Kalshi reports the no-side cost 0.948 -> proceeds = 1 - 0.948 = 0.052
    assert abs(sell_proceeds({"fill_count_fp": "1.00", "taker_fill_cost_dollars": "0.948"}) - 0.052) < 1e-9


def test_sell_proceeds_none_when_no_fill():
    assert sell_proceeds({"fill_count_fp": "0.00"}) is None
