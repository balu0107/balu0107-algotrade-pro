"""Historical OHLCV pulls for backtesting, with a short on-disk cache so
repeated backtest runs during development don't re-hammer yfinance - this
app has already hit yfinance's rate limit twice this session from far
smaller bursts than a multi-symbol, multi-year backtest would produce.
"""
import datetime
import os

import pandas as pd
import yfinance as yf

CACHE_DIR = os.path.join(os.path.dirname(__file__), "_cache")
CACHE_TTL_HOURS = 24


def _cache_path(symbol, period, interval):
    safe = symbol.replace("^", "IDX_")
    return os.path.join(CACHE_DIR, f"{safe}_{period}_{interval}.pkl")


def fetch_history(symbol, period="2y", interval="1d"):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(symbol, period, interval)
    if os.path.exists(path):
        age_hours = (datetime.datetime.utcnow().timestamp() - os.path.getmtime(path)) / 3600
        if age_hours < CACHE_TTL_HOURS:
            return pd.read_pickle(path)

    history = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
    if history is not None and not history.empty:
        history.to_pickle(path)
    return history
