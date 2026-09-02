"""Walk-forward backtest: replays historical daily bars one day at a time.
At each simulated "prediction day" t, every candidate (the production
heuristic plus a few fixed baselines) sees ONLY history up to and including
day t - never day t+1 or later - then its call is checked against the
already-known forward return. No fitting happens anywhere in this file:
every candidate is a fixed rule, so this is a pure out-of-sample evaluation,
not a train/test split (Part 10's "don't jump to ML" - this is the step
before that question is even reachable).

Known, documented scope limits (not silent gaps):
- DELIVERY-timeframe daily bars only. yfinance doesn't retain 5-minute
  intraday history far enough back to backtest the INTRADAY variant of
  build_algo_prediction this way.
- The production heuristic's news-sentiment input is fixed at 0 here - there
  is no historical news archive to replay sentiment from, so this backtest
  only evaluates the price/momentum/Nifty side of build_algo_prediction. A
  "news-only" baseline (mentioned in the original spec) is skipped for the
  same reason.
"""
from app.services.prediction import build_algo_prediction
from app.services.prediction_tracking import direction_correct

from .baselines import BASELINE_FUNCTIONS
from .data import fetch_history

HORIZONS = {"1d": 1, "5d": 5}
MIN_LOOKBACK_DAYS = 20


def _heuristic_direction(history_slice, nifty_is_positive):
    current_price = float(history_slice["Close"].iloc[-1])
    previous_close = float(history_slice["Close"].iloc[-2])
    prediction = build_algo_prediction(history_slice, current_price, previous_close, nifty_is_positive, "DELIVERY", sentiment_score=0)
    return prediction["direction"]


def _actual_return_percent(closes, t, days_ahead):
    if t + days_ahead >= len(closes):
        return None
    entry = closes[t]
    if not entry:
        return None
    return (closes[t + days_ahead] - entry) / entry * 100


def backtest_symbol(symbol, nifty_is_positive_by_date, period="2y", history=None):
    """Runs every candidate against one symbol's full available history.
    Returns per-day, per-candidate, per-horizon outcome records - the raw
    material summarize() aggregates into headline metrics. `history` can be
    injected directly (bypassing the network) for testing."""
    if history is None:
        history = fetch_history(f"{symbol}.NS", period=period)
    if history is None or history.empty or len(history) < MIN_LOOKBACK_DAYS + max(HORIZONS.values()) + 1:
        return []

    closes = history["Close"].tolist()
    dates = [ts.date() for ts in history.index]
    records = []

    for t in range(MIN_LOOKBACK_DAYS, len(history) - 1):
        history_slice = history.iloc[: t + 1]
        nifty_is_positive = nifty_is_positive_by_date.get(dates[t], True)
        closes_so_far = closes[: t + 1]

        candidates = {name: fn(closes_so_far, nifty_is_positive) for name, fn in BASELINE_FUNCTIONS.items()}
        candidates["current_heuristic"] = _heuristic_direction(history_slice, nifty_is_positive)

        for horizon_key, days_ahead in HORIZONS.items():
            return_percent = _actual_return_percent(closes, t, days_ahead)
            if return_percent is None:
                continue
            for candidate_name, predicted_direction in candidates.items():
                if predicted_direction is None:
                    continue
                records.append({
                    "symbol": symbol, "candidate": candidate_name, "horizon": horizon_key,
                    "date": dates[t],
                    "predicted_direction": predicted_direction, "return_percent": return_percent,
                    "correct": direction_correct(predicted_direction, return_percent),
                })
    return records


def _build_nifty_lookup(period="2y"):
    """Nifty's own historical daily bars, reduced to the same
    is-today-positive-vs-yesterday's-close boolean build_price_prediction
    computes live - so the backtest's `nifty_is_positive` input matches
    production semantics instead of being invented for this file."""
    nifty_history = fetch_history("^NSEI", period=period)
    if nifty_history is None or nifty_history.empty:
        return {}
    closes = nifty_history["Close"].tolist()
    dates = [ts.date() for ts in nifty_history.index]
    return {d: (closes[i] >= closes[i - 1] if i > 0 else True) for i, d in enumerate(dates)}


def run_backtest(symbols, period="2y"):
    nifty_lookup = _build_nifty_lookup(period)
    all_records = []
    for symbol in symbols:
        try:
            all_records.extend(backtest_symbol(symbol, nifty_lookup, period=period))
        except Exception as exc:
            print(f"Backtest skipped {symbol}: {exc}")
    return summarize(all_records)


def summarize(records):
    buckets = {}
    for record in records:
        key = (record["candidate"], record["horizon"])
        bucket = buckets.setdefault(key, {"n": 0, "correct": 0, "sum_return_rise": 0.0, "n_rise": 0, "sum_return_fall": 0.0, "n_fall": 0})
        bucket["n"] += 1
        bucket["correct"] += 1 if record["correct"] else 0
        if record["predicted_direction"] == "RISE":
            bucket["sum_return_rise"] += record["return_percent"]
            bucket["n_rise"] += 1
        elif record["predicted_direction"] == "FALL":
            bucket["sum_return_fall"] += record["return_percent"]
            bucket["n_fall"] += 1

    results = []
    for (candidate, horizon), bucket in buckets.items():
        results.append({
            "candidate": candidate, "horizon": horizon, "sample_size": bucket["n"],
            "accuracy_percent": round(bucket["correct"] / bucket["n"] * 100, 2) if bucket["n"] else None,
            "avg_return_when_predicted_rise_percent": round(bucket["sum_return_rise"] / bucket["n_rise"], 3) if bucket["n_rise"] else None,
            "avg_return_when_predicted_fall_percent": round(bucket["sum_return_fall"] / bucket["n_fall"], 3) if bucket["n_fall"] else None,
        })
    return sorted(results, key=lambda r: (r["horizon"], r["candidate"]))
