"""Client tests: URL/path/body building (no network) + the V2 order translation.

The order-translation tests mirror a battle-tested production client's unit tests
(the validated reference for the Kalshi V2 YES-referenced mapping). See docs/gotchas.md #1.
"""
import pytest

from kalshi.auth import load_private_key
from kalshi.client import (
    BASE_URLS,
    KalshiError,
    KalshiHttpClient,
    fp,
    normalize_order_response,
    our_fill_price,
    position_contracts,
    synth_status,
    to_v2_order_body,
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


def test_fills_builds_query(client):
    client.fills(ticker="ABC", order_id="oid")
    assert client.captured["method"] == "GET"
    assert client.captured["path"] == "/trade-api/v2/portfolio/fills?ticker=ABC&order_id=oid"


# --- place_order: V2 wire format (the deprecated v1 shape is gone) ---
def test_place_order_posts_v2_body_and_path(client):
    client.place_order("ABC", "yes", "sell", 1, yes_price=5, client_order_id="cid")
    assert client.captured["method"] == "POST"
    # V2 create endpoint (NOT the sunset /portfolio/orders).
    assert client.captured["path"] == "/trade-api/v2/portfolio/events/orders"
    # YES sell 5c -> ask @ 0.0500; count is a fixed-point STRING; STP required.
    assert client.captured["body"] == {
        "ticker": "ABC",
        "side": "ask",
        "count": "1.00",
        "price": "0.0500",
        "self_trade_prevention_type": "taker_at_cross",
        "time_in_force": "immediate_or_cancel",
        "client_order_id": "cid",
    }


def test_place_order_autogenerates_client_order_id(client):
    client.place_order("ABC", "no", "buy", 2, no_price=40)
    body = client.captured["body"]
    assert body["client_order_id"]                    # auto uuid
    # NO buy 40c -> ask @ (1 - 0.40) = 0.6000, count "2.00".
    assert body["side"] == "ask"
    assert body["price"] == "0.6000"
    assert body["count"] == "2.00"
    # intent-vocabulary fields never reach the wire; post_only omitted when unset.
    assert "yes_price" not in body and "no_price" not in body and "action" not in body
    assert "post_only" not in body


def test_place_order_normalizes_response(client):
    # Stub a filled V2 response and check the normalized dict the caller gets.
    client._request = lambda m, p, body=None: {
        "order_id": "o-1", "client_order_id": "cid",
        "fill_count": "1.00", "remaining_count": "0.00",
        "average_fill_price": "0.0500", "average_fee_paid": "0.0100",
    }
    out = client.place_order("ABC", "no", "buy", 1, no_price=95, client_order_id="cid")
    assert out["order_id"] == "o-1"
    assert out["status"] == "executed"            # synthesized (V2 omits status)
    assert out["fill_count"] == 1.0
    # NO order: our price = 1 - average_fill_price = 0.95.
    assert abs(out["fill_price"] - 0.95) < 1e-9
    assert abs(out["fees"] - 0.01) < 1e-9          # per-ct 0.01 x 1 filled


def test_cancel_uses_v2_delete_path(client):
    def fake(method, path, body=None):
        client.captured.update(method=method, path=path, body=body)
        return {"order_id": "oid", "reduced_by": "1.00"}

    client._request = fake
    out = client.cancel_order("oid")
    assert client.captured["method"] == "DELETE"
    assert client.captured["path"] == "/trade-api/v2/portfolio/events/orders/oid"
    assert out["reduced_count"] == 1.0
    assert out["status"] == "canceled"


def test_from_env_requires_api_key(monkeypatch):
    monkeypatch.delenv("KALSHI_API_KEY", raising=False)
    with pytest.raises(KalshiError):
        KalshiHttpClient.from_env()


# --- V2 translation: side/action -> bid/ask + YES-referenced price ---
def test_v2_body_maps_all_four_side_action_combos():
    def body(side, action, **price):
        return to_v2_order_body("KX-T", side, action, 1, **price)

    b = body("yes", "buy", yes_price=50)
    assert b["side"] == "bid" and b["price"] == "0.5000"
    assert b["count"] == "1.00" and b["self_trade_prevention_type"] == "taker_at_cross"

    b = body("yes", "sell", yes_price=85)
    assert b["side"] == "ask" and b["price"] == "0.8500"

    b = body("no", "buy", no_price=30)      # buy NO @ 30 == ask @ 0.70
    assert b["side"] == "ask" and b["price"] == "0.7000"

    b = body("no", "sell", no_price=30)     # sell NO @ 30 == bid @ 0.70
    assert b["side"] == "bid" and b["price"] == "0.7000"


def test_v2_body_preserves_decicent_and_flips_no():
    # YES sell deci-cent 0.9980 -> ask 0.9980 (precision survives), post_only kept.
    b = to_v2_order_body("KX-T", "yes", "sell", 1, yes_price_dollars="0.9980",
                         time_in_force="good_till_canceled", post_only=True)
    assert b["side"] == "ask" and b["price"] == "0.9980" and b["post_only"] is True
    assert b["time_in_force"] == "good_till_canceled"
    # NO sell deci-cent 0.9980 -> bid @ (1 - 0.998) = 0.0020 (exact integer flip).
    b = to_v2_order_body("KX-T", "no", "sell", 1, no_price_dollars="0.9980")
    assert b["side"] == "bid" and b["price"] == "0.0020"


def test_v2_body_rejects_missing_price():
    with pytest.raises(ValueError):
        to_v2_order_body("KX-T", "yes", "buy", 1)


def test_v2_body_rejects_out_of_range_price():
    with pytest.raises(ValueError):
        to_v2_order_body("KX-T", "yes", "buy", 1, yes_price=100)   # -> 1.0000, not in (0,1)


def test_v2_body_rejects_bad_action():
    with pytest.raises(ValueError):
        to_v2_order_body("KX-T", "yes", "hold", 1, yes_price=50)


# --- status synthesis (V2 omits `status`) ---
def test_synth_status_from_fill_and_tif():
    ioc, gtc = "immediate_or_cancel", "good_till_canceled"
    assert synth_status({"fill_count": "1.00", "remaining_count": "0.00"}, ioc) == "executed"
    assert synth_status({"fill_count": "0.00", "remaining_count": "0.00"}, ioc) == "canceled"
    assert synth_status({"fill_count": "1.00", "remaining_count": "1.00"}, ioc) == "canceled"
    assert synth_status({"fill_count": "0.00", "remaining_count": "1.00"}, gtc) == "resting"


# --- our realized price + the fill_cost identity (one rule, both sides) ---
def test_our_fill_price_one_rule_both_sides():
    # average_fill_price is YES-referenced.
    assert abs(our_fill_price("yes", {"average_fill_price": "0.9300"}) - 0.93) < 1e-9
    assert abs(our_fill_price("no", {"average_fill_price": "0.0700"}) - 0.93) < 1e-9
    assert our_fill_price("yes", {}) is None        # unfilled


def test_fill_price_identity_holds_for_buy_and_sell():
    # The old v1 proceeds were `1 - taker_fill_cost/filled`. our_fill_price must
    # reproduce the per-side realized price for every side/action combo.
    # YES sell, avg 0.93 -> 0.93 ; NO sell, YES-ref 0.07 -> 0.93.
    assert abs(our_fill_price("yes", {"average_fill_price": "0.9300"}) - 0.93) < 1e-9
    assert abs(our_fill_price("no", {"average_fill_price": "0.0700"}) - 0.93) < 1e-9
    # YES buy, avg 0.93 -> 0.93 ; NO buy, YES-ref 0.05 -> 0.95.
    assert abs(our_fill_price("yes", {"average_fill_price": "0.9300"}) - 0.93) < 1e-9
    assert abs(our_fill_price("no", {"average_fill_price": "0.0500"}) - 0.95) < 1e-9


def test_normalize_totals_fees_from_per_contract():
    resp = {
        "order_id": "o", "fill_count": "3.00", "remaining_count": "0.00",
        "average_fill_price": "0.5000", "average_fee_paid": "0.0200",
    }
    out = normalize_order_response("yes", "buy", "immediate_or_cancel", resp)
    assert out["status"] == "executed"
    assert abs(out["fill_price"] - 0.5) < 1e-9
    assert abs(out["fees"] - 0.06) < 1e-9            # per-ct 0.02 x 3 filled
    assert out["raw"] is resp


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
