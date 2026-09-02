"""Run from backend/: `.venv/Scripts/python.exe -m research.run_backtest`

Prints a plain-text comparison: for each horizon (1d/5d), how buy-and-hold,
5-day momentum, MA-trend, and the app's own production heuristic actually
performed against real historical daily bars. This is the first real,
historical answer to "does any of this beat a coin flip" - see
research/backtest.py's docstring for what's deliberately out of scope this
pass (intraday timeframe, historical news sentiment).
"""
from app.services.ranking import NSE_SYMBOLS

from .backtest import run_backtest

# Keeps runtime/rate-limit exposure reasonable - each symbol is its own
# yfinance history() call (cached 24h by research/data.py on repeat runs).
# Pass a larger slice of NSE_SYMBOLS (or the full FULL_NSE_SYMBOLS list) for
# a wider sample; nothing below is hardcoded to this particular size.
DEFAULT_SAMPLE_SIZE = 40


def main():
    universe = [symbol for symbol, _ in NSE_SYMBOLS[:DEFAULT_SAMPLE_SIZE]]
    print(f"Backtesting {len(universe)} symbols over 2 years of daily bars (DELIVERY timeframe only)...\n")
    results = run_backtest(universe, period="2y")

    header = f"{'horizon':<8}{'candidate':<18}{'n':>7}{'accuracy%':>11}{'avg_ret|RISE%':>15}{'avg_ret|FALL%':>15}"
    print(header)
    print("-" * len(header))
    for row in results:
        def fmt(value):
            return f"{value:.2f}" if value is not None else "-"
        print(
            f"{row['horizon']:<8}{row['candidate']:<18}{row['sample_size']:>7}"
            f"{fmt(row['accuracy_percent']):>11}"
            f"{fmt(row['avg_return_when_predicted_rise_percent']):>15}"
            f"{fmt(row['avg_return_when_predicted_fall_percent']):>15}"
        )
    print("\nAccuracy is the direction-correct rate. avg_ret|RISE/FALL is the mean actual "
          "forward return on the days each candidate called that direction - not a backtest "
          "P&L (no position sizing, costs, or slippage modeled).")


if __name__ == "__main__":
    main()
