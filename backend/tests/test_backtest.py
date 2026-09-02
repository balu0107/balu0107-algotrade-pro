"""Tests for the walk-forward backtest engine (research/backtest.py). All
synthetic - no network calls, no dependency on research/data.py's yfinance
fetch. The most important test here is the no-lookahead one: it proves a
prediction made at day t is unaffected by anything that happens after t,
which is the entire point of a walk-forward backtest.

Run from backend/: `.venv/Scripts/python.exe -m pytest tests/test_backtest.py -v`
"""
import pandas as pd
import pytest

from research import baselines
from research.backtest import _actual_return_percent, backtest_symbol, summarize

ALWAYS_POSITIVE_NIFTY = {}  # backtest_symbol defaults to True when a date is missing


def make_history(closes, start="2024-01-01"):
    dates = pd.bdate_range(start=start, periods=len(closes))
    return pd.DataFrame({
        "Open": closes, "High": [c * 1.01 for c in closes], "Low": [c * 0.99 for c in closes],
        "Close": closes, "Volume": [100_000] * len(closes),
    }, index=dates)


# --- baselines ---------------------------------------------------------

def test_buy_and_hold_always_rises():
    assert baselines.buy_and_hold([100, 90, 80], True) == "RISE"


def test_momentum_follows_trailing_return():
    rising = [100, 101, 102, 103, 104, 105]
    falling = [105, 104, 103, 102, 101, 100]
    assert baselines.momentum(rising, True, lookback=5) == "RISE"
    assert baselines.momentum(falling, True, lookback=5) == "FALL"


def test_ma_trend_compares_fast_and_slow_averages():
    closes = [100] * 15 + [110] * 5  # fast average pulled up by the recent jump
    assert baselines.ma_trend(closes, True, fast=5, slow=20) == "RISE"


# --- return computation --------------------------------------------------

def test_actual_return_percent_computes_forward_move():
    closes = [100, 100, 100, 110, 100, 100, 90]
    assert _actual_return_percent(closes, 2, 1) == pytest.approx(10.0)


def test_actual_return_percent_none_past_end_of_series():
    closes = [100, 101, 102]
    assert _actual_return_percent(closes, 1, 5) is None


# --- backtest_symbol: end-to-end on synthetic data -----------------------

def test_backtest_symbol_produces_records_for_every_candidate_and_horizon():
    closes = [100 + i * 0.5 for i in range(40)]  # steady uptrend, plenty of history
    history = make_history(closes)
    records = backtest_symbol("SYN", ALWAYS_POSITIVE_NIFTY, history=history)
    assert records
    assert {r["candidate"] for r in records} == {"buy_and_hold", "momentum_5d", "ma_trend", "current_heuristic"}
    assert {r["horizon"] for r in records} == {"1d", "5d"}


def test_backtest_symbol_too_short_history_returns_empty():
    history = make_history([100, 101, 102])  # far below MIN_LOOKBACK_DAYS + horizon
    assert backtest_symbol("SYN", ALWAYS_POSITIVE_NIFTY, history=history) == []


def test_buy_and_hold_correctness_matches_actual_direction():
    """buy_and_hold always predicts RISE, so its "correct" flag should just
    mirror whether the actual forward return was positive."""
    closes = [100 + i for i in range(30)] + [200] + [50] * 20  # sharp reversal partway through
    history = make_history(closes)
    records = backtest_symbol("SYN", ALWAYS_POSITIVE_NIFTY, history=history)
    buy_hold_records = [r for r in records if r["candidate"] == "buy_and_hold"]
    assert buy_hold_records
    for r in buy_hold_records:
        assert r["correct"] == (r["return_percent"] > 0)


# --- the core guarantee: no look-ahead -----------------------------------

def test_predictions_before_the_divergence_point_are_identical_regardless_of_future_data():
    """The defining property of a walk-forward backtest: what a candidate
    predicts at day t must depend only on data up to and including day t.
    Two histories that are identical through day 30 but wildly different
    afterward must produce identical predictions, per candidate, for every
    date inside that shared prefix - if a candidate ever peeked forward,
    the wildly different tails (500 vs. 10) would make these diverge."""
    shared_prefix = [100 + i * 0.3 for i in range(31)]  # days 0..30
    history_a = make_history(shared_prefix + [500] * 9)
    history_b = make_history(shared_prefix + [10] * 9)

    records_a = backtest_symbol("SYN", ALWAYS_POSITIVE_NIFTY, history=history_a)
    records_b = backtest_symbol("SYN", ALWAYS_POSITIVE_NIFTY, history=history_b)

    shared_dates = {ts.date() for ts in history_a.index[:31]}

    def predictions_by_key(records):
        return {(r["candidate"], r["date"]): r["predicted_direction"] for r in records if r["date"] in shared_dates}

    preds_a = predictions_by_key(records_a)
    preds_b = predictions_by_key(records_b)
    assert preds_a  # sanity: the shared prefix actually produced predictions to compare
    assert preds_a == preds_b


# --- summarize -------------------------------------------------------------

def test_summarize_aggregates_accuracy_and_conditional_returns():
    records = [
        {"symbol": "A", "candidate": "buy_and_hold", "horizon": "1d", "predicted_direction": "RISE", "return_percent": 2.0, "correct": True},
        {"symbol": "A", "candidate": "buy_and_hold", "horizon": "1d", "predicted_direction": "RISE", "return_percent": -1.0, "correct": False},
        {"symbol": "B", "candidate": "buy_and_hold", "horizon": "1d", "predicted_direction": "RISE", "return_percent": 4.0, "correct": True},
    ]
    summary = summarize(records)
    row = next(r for r in summary if r["candidate"] == "buy_and_hold" and r["horizon"] == "1d")
    assert row["sample_size"] == 3
    assert row["accuracy_percent"] == pytest.approx(200 / 3, abs=0.01)
    assert row["avg_return_when_predicted_rise_percent"] == pytest.approx((2.0 - 1.0 + 4.0) / 3, abs=0.001)
    assert row["avg_return_when_predicted_fall_percent"] is None


def test_summarize_empty_input_returns_empty_list():
    assert summarize([]) == []
