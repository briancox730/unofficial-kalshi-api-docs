"""Orderbook tests: bids-only complement asks + exact fractional-delta accumulation."""
from kalshi.orderbook import OrderBook, to_mills


def test_to_mills_handles_string_and_number_and_decicent():
    assert to_mills("0.62") == 620
    assert to_mills(0.62) == 620
    assert to_mills("0.998") == 998  # 0.001 deci-cent tick preserved exactly


def test_snapshot_best_bids():
    book = OrderBook("T")
    book.apply_snapshot(yes_levels=[["0.62", 10], ["0.61", 5]], no_levels=[["0.37", 8]])
    assert book.best_yes_bid() == 0.62
    assert book.best_no_bid() == 0.37


def test_asks_are_the_complement_of_the_other_side():
    book = OrderBook("T")
    book.apply_snapshot(yes_levels=[["0.40", 1]], no_levels=[["0.37", 8]])
    assert book.yes_ask() == 0.63  # 1 - best_no_bid
    assert book.no_ask() == 0.60   # 1 - best_yes_bid


def test_delta_nets_to_zero_and_removes_level():
    book = OrderBook("T")
    book.apply_snapshot(yes_levels=[["0.62", 10]])
    book.apply_delta("yes", "0.62", -10)
    assert 620 not in book.yes_bids
    assert book.best_yes_bid() is None


def test_fractional_deltas_leave_no_phantom_residual():
    book = OrderBook("T")
    book.apply_delta("no", "0.30", 74.77)
    book.apply_delta("no", "0.30", -74.77)
    assert 300 not in book.no_bids  # exact accumulation -> clean removal


def test_partial_delta_keeps_remaining_size():
    book = OrderBook("T")
    book.apply_snapshot(no_levels=[["0.30", 5.0]])
    book.apply_delta("no", "0.30", -2.5)
    assert abs(book.no_bids[300] - 2.5) < 1e-9


def test_string_typed_delta_is_parsed():
    book = OrderBook("T")
    book.apply_delta("yes", "0.50", "3.5")  # delta as a string
    assert abs(book.yes_bids[500] - 3.5) < 1e-9


def test_empty_book_reads_none():
    book = OrderBook("T")
    assert book.best_yes_bid() is None
    assert book.yes_ask() is None
    assert book.top() == {"yes_bid": None, "yes_ask": None, "no_bid": None, "no_ask": None}
