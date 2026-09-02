"""Simple, parameter-free directional baselines. Each takes only the closes
seen up to and including "today" (never a peek forward) and returns a
RISE/FALL call. None of these are fitted or tuned - they're fixed rules, so
there is no train/test split to worry about; the backtest evaluates them
out-of-sample by construction, at every simulated day, for the entire
history.
"""


def buy_and_hold(closes, nifty_is_positive):
    """The reference floor: always predicts RISE. If a real signal can't
    beat "the market generally goes up," it isn't adding anything."""
    return "RISE"


def momentum(closes, nifty_is_positive, lookback=5):
    """Continuation: predicts the same direction as the trailing N-day
    return."""
    if len(closes) <= lookback:
        return "RISE"
    change = closes[-1] - closes[-1 - lookback]
    return "RISE" if change >= 0 else "FALL"


def ma_trend(closes, nifty_is_positive, fast=5, slow=20):
    """Predicts RISE when the fast moving average sits above the slow one -
    the same MA-relationship signal build_algo_prediction blends in as one
    of several inputs, tested here on its own."""
    if len(closes) < slow:
        return "RISE"
    fast_avg = sum(closes[-fast:]) / fast
    slow_avg = sum(closes[-slow:]) / slow
    return "RISE" if fast_avg >= slow_avg else "FALL"


BASELINE_FUNCTIONS = {
    "buy_and_hold": buy_and_hold,
    "momentum_5d": momentum,
    "ma_trend": ma_trend,
}
