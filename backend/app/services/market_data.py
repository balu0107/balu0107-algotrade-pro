"""Shared, short-TTL cache in front of yfinance's `.info`/`.history()` calls.

Before this, opening one stock's detail page could trigger 2-3 independent
yf.Ticker() fetches for the *same* symbol within the same few seconds
(stock detail, candles, news-sentiment each built their own Ticker with zero
sharing), and the alert checker re-fetched `.info` separately for every
active alert even when several alerts watched the same symbol. That
redundant traffic is a direct contributor to the yfinance rate-limiting this
app has hit twice this session. This module doesn't change what any route
returns - it only collapses near-duplicate live fetches that happen seconds
apart into one.

TTLs are deliberately short (20-60s), well under the existing route-level
caches (e.g. the stock-detail route's own 90s cache) - this is not meant to
replace those longer caches, only to catch the redundancy *between* routes
that each already cache themselves independently.
"""
import datetime

import yfinance as yf

INFO_CACHE_SECONDS = 20
HISTORY_CACHE_SECONDS = 60

_info_cache = {}
_history_cache = {}


def get_ticker(symbol):
    """A yf.Ticker wrapper holds no network state itself - constructing one
    is cheap. What actually hits the network (.info, .history()) is cached
    below, keyed off the exact symbol string passed in."""
    return yf.Ticker(symbol)


def get_info(symbol):
    now = datetime.datetime.utcnow()
    cached = _info_cache.get(symbol)
    if cached and (now - cached["computed_at"]).total_seconds() < INFO_CACHE_SECONDS:
        return cached["info"]
    info = get_ticker(symbol).info
    _info_cache[symbol] = {"info": info, "computed_at": now}
    return info


def get_history(symbol, period, interval):
    key = (symbol, period, interval)
    now = datetime.datetime.utcnow()
    cached = _history_cache.get(key)
    if cached and (now - cached["computed_at"]).total_seconds() < HISTORY_CACHE_SECONDS:
        return cached["history"]
    history = get_ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
    _history_cache[key] = {"history": history, "computed_at": now}
    return history
