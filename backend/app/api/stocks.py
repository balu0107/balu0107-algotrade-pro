import concurrent.futures
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from ..models import UserDB
from ..security import get_current_user
from ..services import market_data
from ..services.prediction import build_candles, build_fundamentals, build_price_prediction, CANDLE_RANGES
from ..services.ranking import FULL_NSE_SYMBOLS, SYMBOL_TO_NAME, _market_scan_cache

router = APIRouter()


@router.get("/api/symbols/search")
def search_symbols(q: str = "", current_user: UserDB = Depends(get_current_user)):
    query = q.strip().upper()
    if not query:
        return []

    starts_with = [s for s in FULL_NSE_SYMBOLS if s[0].startswith(query)]
    contains = [s for s in FULL_NSE_SYMBOLS if query in s[0] or query in s[1].upper()]

    # Reuse whatever the market scan already has cached - never trigger a fresh
    # scan here, or every keystroke would hammer yfinance for up to 8 symbols.
    quote_lookup = {item["symbol"]: item for item in _market_scan_cache["data"]}

    seen = set()
    results = []
    for symbol, name in starts_with + contains:
        if symbol in seen: continue
        seen.add(symbol)
        quote = quote_lookup.get(symbol)
        results.append({
            "symbol": symbol,
            "name": name,
            "current_price": quote["current_price"] if quote else None,
            "percent_change": quote["percent_change"] if quote else None,
        })
        if len(results) >= 8: break

    return results


MAX_QUOTE_SYMBOLS_PER_REQUEST = 60  # bounds worst-case cost - callers only ever need what's actually on screen


def _fetch_one_quote(symbol: str):
    try:
        query_symbol = f"{symbol}.NS" if not symbol.endswith(".NS") else symbol
        info = market_data.get_info(query_symbol)
        current_price = info.get("currentPrice", info.get("regularMarketPrice", 0))
        prev_close = info.get("previousClose", 0)
        if not current_price:
            return None
        return symbol, {
            "current_price": round(current_price, 2),
            "percent_change": round((current_price - prev_close) / prev_close * 100, 2) if prev_close else 0,
        }
    except Exception:
        return None


@router.get("/api/quotes")
def get_quotes(symbols: str = Query(...), current_user: UserDB = Depends(get_current_user)):
    """Cheap, price-only batch lookup for refreshing rows already on screen
    (Top Picks/Falls/F&O) without re-running the full scan or prediction
    algorithm - those only recompute once a day, but a stock's price moves
    all day, so this exists specifically to keep the displayed price live in
    between. Reuses market_data's 20s .info cache, so this never costs more
    than one fresh yfinance call per symbol per 20s no matter how many tabs
    ask for the same symbol. One symbol's failure (bad ticker, transient
    error) is silently omitted rather than failing the whole batch."""
    requested = [s.strip().upper() for s in symbols.split(",") if s.strip()][:MAX_QUOTE_SYMBOLS_PER_REQUEST]
    quotes = {}
    if requested:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            for result in executor.map(_fetch_one_quote, requested):
                if result:
                    symbol, quote = result
                    quotes[symbol] = quote
    return {"quotes": quotes}


STOCK_DETAIL_CACHE_SECONDS = 90  # short-lived cache, same TTL-dict idiom as the rest of this file
_stock_detail_cache = {}


def _fetch_stock_data(symbol: str):
    """The actual live yfinance fetch + prediction build. Raises on any
    failure (rate-limited, bad symbol, network) - get_stock_data below is
    what decides whether that failure is fatal or falls back to a cached
    last-known-good response."""
    query_symbol = f"{symbol.upper()}.NS" if not symbol.upper().endswith('.NS') else symbol.upper()

    stock = market_data.get_ticker(query_symbol)
    stock_info = market_data.get_info(query_symbol)

    current_price = stock_info.get('currentPrice', stock_info.get('regularMarketPrice', 0))
    open_price = stock_info.get('open', 0)
    high_price = stock_info.get('dayHigh', 0)
    low_price = stock_info.get('dayLow', 0)
    prev_close = stock_info.get('previousClose', 0)
    volume = stock_info.get('volume', stock_info.get('regularMarketVolume', 0))

    percent_change = ((current_price - prev_close) / prev_close) * 100 if prev_close else 0

    nifty_info = market_data.get_info("^NSEI")
    nifty_current = nifty_info.get('regularMarketPrice', nifty_info.get('currentPrice', 0))
    nifty_prev = nifty_info.get('previousClose', 0)

    nifty_change = nifty_current - nifty_prev
    nifty_is_positive = nifty_change >= 0

    # Advanced Algorithmic Prediction
    company_name = SYMBOL_TO_NAME.get(symbol.upper(), symbol.upper())
    prediction = build_price_prediction(stock, current_price, prev_close, nifty_is_positive, symbol, company_name, stock_info.get("sector"))
    fundamentals = build_fundamentals(stock_info)

    # Suggestion text is derived from that same active-timeframe algorithm,
    # not a separate heuristic - it used to be its own OHL-vs-Nifty check
    # (open vs. day's low/high, current vs. previous close) that could,
    # and did, disagree with the algorithm's own direction/confidence for
    # the same stock at the same instant. One signal, not two.
    active_prediction = prediction[prediction["active"].lower()]
    direction = active_prediction["direction"]
    confidence = active_prediction["confidence"]

    if direction == "RISE":
        suggestion = "STRONG BUY (High Confidence)" if confidence == "High" else "BUY (Positive Momentum)"
    elif direction == "FALL":
        suggestion = "DON'T BUY / SHORT IT" if confidence == "High" else "DON'T BUY (Negative Momentum)"
    else:
        suggestion = "HOLD (No Clear Trend)"

    return {
        "symbol": query_symbol.replace('.NS', ''),
        "current_price": round(current_price, 2),
        "open": round(open_price, 2),
        "high": round(high_price, 2),
        "low": round(low_price, 2),
        "previous_close": round(prev_close, 2),
        "percent_change": round(percent_change, 2),
        "volume": volume,
        "suggestion": suggestion,
        "prediction": prediction,
        "fundamentals": fundamentals,
        "nifty": {
            "value": round(nifty_current, 2),
            "change": round(nifty_change, 2),
            "is_positive": nifty_is_positive
        }
    }


@router.get("/api/stock/{symbol}")
def get_stock_data(symbol: str, current_user: UserDB = Depends(get_current_user)):
    symbol_upper = symbol.upper()
    now = datetime.datetime.utcnow()
    cached = _stock_detail_cache.get(symbol_upper)

    if cached and (now - cached["computed_at"]).total_seconds() < STOCK_DETAIL_CACHE_SECONDS:
        return cached["data"]

    try:
        result = _fetch_stock_data(symbol)
        result["stale"] = False
        result["stale_reason"] = None
        _stock_detail_cache[symbol_upper] = {"data": result, "computed_at": now}
        return result
    except Exception as e:
        # A live fetch failing (rate-limited, transient network issue) isn't
        # the same as this symbol never having loaded at all - if we have a
        # previously-good response for it, that's still far more useful to
        # show than a bare error, clearly labeled as stale rather than
        # silently passed off as current.
        if cached:
            fallback = dict(cached["data"])
            fallback["stale"] = True
            fallback["stale_reason"] = f"Live data temporarily unavailable ({str(e)[:150]}) - showing last known values from {cached['computed_at'].isoformat()}."
            return fallback
        raise HTTPException(status_code=404, detail=f"Stock data not found: {str(e)}")


@router.get("/api/stock/{symbol}/candles")
def get_stock_candles(symbol: str, range: str = Query(default="1M"), current_user: UserDB = Depends(get_current_user)):
    try:
        query_symbol = f"{symbol.upper()}.NS" if not symbol.upper().endswith('.NS') else symbol.upper()
        range_key = range.upper() if range.upper() in CANDLE_RANGES else "1M"
        stock = market_data.get_ticker(query_symbol)
        candles = build_candles(stock, range_key)
        return {
            "symbol": query_symbol.replace('.NS', ''),
            "range": range_key,
            "available_ranges": list(CANDLE_RANGES.keys()),
            "candles": candles,
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Candle data not found: {str(e)}")
