"""The NSE symbol directory, the market/daily scans, and direction-based
ranking. Moved verbatim from main.py (Phase 2A, no behavior change).
"""
import concurrent.futures
import csv
import datetime
import io

import requests

from ..database import SessionLocal
from ..models import PriceHistoryDB
from . import market_data
from .prediction import build_algo_prediction, get_cached_news_sentiment, get_market_phase, is_market_open_now
from .prediction_tracking import record_daily_predictions

# --- NSE SYMBOL DIRECTORY (for search-as-you-type suggestions) ---
NSE_SYMBOLS = [
    ("RELIANCE", "Reliance Industries"), ("TCS", "Tata Consultancy Services"), ("HDFCBANK", "HDFC Bank"),
    ("ICICIBANK", "ICICI Bank"), ("INFY", "Infosys"), ("HINDUNILVR", "Hindustan Unilever"),
    ("ITC", "ITC Limited"), ("SBIN", "State Bank of India"), ("BHARTIARTL", "Bharti Airtel"),
    ("KOTAKBANK", "Kotak Mahindra Bank"), ("LT", "Larsen & Toubro"), ("AXISBANK", "Axis Bank"),
    ("BAJFINANCE", "Bajaj Finance"), ("ASIANPAINT", "Asian Paints"), ("MARUTI", "Maruti Suzuki"),
    ("HCLTECH", "HCL Technologies"), ("SUNPHARMA", "Sun Pharmaceutical"), ("TITAN", "Titan Company"),
    ("ULTRACEMCO", "UltraTech Cement"), ("WIPRO", "Wipro"), ("NESTLEIND", "Nestle India"),
    ("ONGC", "Oil & Natural Gas Corp"), ("NTPC", "NTPC Limited"), ("POWERGRID", "Power Grid Corp"),
    ("M&M", "Mahindra & Mahindra"), ("TATAMOTORS", "Tata Motors"), ("TATASTEEL", "Tata Steel"),
    ("ADANIENT", "Adani Enterprises"), ("ADANIPORTS", "Adani Ports"), ("JSWSTEEL", "JSW Steel"),
    ("BAJAJFINSV", "Bajaj Finserv"), ("HDFCLIFE", "HDFC Life Insurance"), ("SBILIFE", "SBI Life Insurance"),
    ("DIVISLAB", "Divi's Laboratories"), ("DRREDDY", "Dr Reddy's Laboratories"), ("CIPLA", "Cipla"),
    ("EICHERMOT", "Eicher Motors"), ("HEROMOTOCO", "Hero MotoCorp"), ("BAJAJ-AUTO", "Bajaj Auto"),
    ("GRASIM", "Grasim Industries"), ("COALINDIA", "Coal India"), ("BPCL", "Bharat Petroleum"),
    ("IOC", "Indian Oil Corp"), ("HINDALCO", "Hindalco Industries"), ("TECHM", "Tech Mahindra"),
    ("BRITANNIA", "Britannia Industries"), ("APOLLOHOSP", "Apollo Hospitals"), ("UPL", "UPL Limited"),
    ("SHREECEM", "Shree Cement"), ("INDUSINDBK", "IndusInd Bank"), ("TATACONSUM", "Tata Consumer Products"),
    ("VEDL", "Vedanta Limited"), ("PIDILITIND", "Pidilite Industries"), ("DABUR", "Dabur India"),
    ("GODREJCP", "Godrej Consumer Products"), ("MARICO", "Marico Limited"), ("HAVELLS", "Havells India"),
    ("SIEMENS", "Siemens India"), ("DLF", "DLF Limited"), ("AMBUJACEM", "Ambuja Cements"),
    ("BANKBARODA", "Bank of Baroda"), ("PNB", "Punjab National Bank"), ("CANBK", "Canara Bank"),
    ("IDFCFIRSTB", "IDFC First Bank"), ("BANDHANBNK", "Bandhan Bank"), ("FEDERALBNK", "Federal Bank"),
    ("ZOMATO", "Zomato"), ("NYKAA", "FSN E-Commerce (Nykaa)"), ("PAYTM", "One97 Communications (Paytm)"),
    ("POLICYBZR", "PB Fintech (Policybazaar)"), ("IRCTC", "Indian Railway Catering & Tourism"),
    ("DMART", "Avenue Supermarts (DMart)"), ("TRENT", "Trent Limited"), ("PGHH", "Procter & Gamble Hygiene"),
    ("COLPAL", "Colgate-Palmolive India"), ("BERGEPAINT", "Berger Paints"), ("MUTHOOTFIN", "Muthoot Finance"),
    ("CHOLAFIN", "Cholamandalam Investment"), ("LICHSGFIN", "LIC Housing Finance"), ("SRTRANSFIN", "Shriram Finance"),
    ("PEL", "Piramal Enterprises"), ("LUPIN", "Lupin Limited"), ("AUROPHARMA", "Aurobindo Pharma"),
    ("BIOCON", "Biocon Limited"), ("TORNTPHARM", "Torrent Pharmaceuticals"), ("ALKEM", "Alkem Laboratories"),
    ("MPHASIS", "Mphasis Limited"), ("LTIM", "LTIMindtree"), ("PERSISTENT", "Persistent Systems"),
    ("COFORGE", "Coforge Limited"), ("OFSS", "Oracle Financial Services"), ("NAUKRI", "Info Edge (Naukri)"),
    ("INDIGO", "InterGlobe Aviation (IndiGo)"), ("SPICEJET", "SpiceJet"), ("IRFC", "Indian Railway Finance Corp"),
    ("RVNL", "Rail Vikas Nigam"), ("BEL", "Bharat Electronics"), ("HAL", "Hindustan Aeronautics"),
    ("BHEL", "Bharat Heavy Electricals"), ("SAIL", "Steel Authority of India"), ("NMDC", "NMDC Limited"),
    ("JINDALSTEL", "Jindal Steel & Power"), ("NATIONALUM", "National Aluminium"), ("GAIL", "GAIL India"),
    ("PETRONET", "Petronet LNG"), ("IGL", "Indraprastha Gas"), ("MGL", "Mahanagar Gas"),
    ("ZEEL", "Zee Entertainment"), ("SUNTV", "Sun TV Network"), ("PVRINOX", "PVR Inox"),
    ("YESBANK", "Yes Bank"), ("IDEA", "Vodafone Idea"), ("SUZLON", "Suzlon Energy"),
    ("JIOFIN", "Jio Financial Services"), ("BSE", "BSE Limited"), ("CDSL", "Central Depository Services"),
    ("ANGELONE", "Angel One"), ("MCX", "Multi Commodity Exchange"), ("IEX", "Indian Energy Exchange"),
    ("DIXON", "Dixon Technologies"), ("KPITTECH", "KPIT Technologies"), ("TATAELXSI", "Tata Elxsi"),
    ("ASTRAL", "Astral Limited"), ("POLYCAB", "Polycab India"), ("VOLTAS", "Voltas Limited"),
    ("BLUESTARCO", "Blue Star Limited"), ("WHIRLPOOL", "Whirlpool India"), ("CROMPTON", "Crompton Greaves"),
    ("PAGEIND", "Page Industries"), ("ABFRL", "Aditya Birla Fashion"), ("RELAXO", "Relaxo Footwears"),
    ("BATAINDIA", "Bata India"), ("JUBLFOOD", "Jubilant FoodWorks"), ("VBL", "Varun Beverages"),
    ("UNITDSPR", "United Spirits"), ("MCDOWELL-N", "United Spirits (McDowell)"), ("GLAND", "Gland Pharma"),
    ("SYNGENE", "Syngene International"), ("LAURUSLABS", "Laurus Labs"), ("IPCALAB", "IPCA Laboratories"),
    ("ABBOTINDIA", "Abbott India"), ("PFIZER", "Pfizer India"), ("GSK", "GlaxoSmithKline Pharma"),
    ("SANOFI", "Sanofi India"), ("NHPC", "NHPC Limited"), ("SJVN", "SJVN Limited"),
    ("TATAPOWER", "Tata Power"), ("ADANIGREEN", "Adani Green Energy"), ("ADANIPOWER", "Adani Power"),
    ("ADANITRANS", "Adani Transmission"), ("TORNTPOWER", "Torrent Power"), ("CESC", "CESC Limited"),
]

# --- FULL NSE EQUITY DIRECTORY (real ~2,300 symbol universe, not the ~128
# curated shortlist above) ---
NSE_EQUITY_LIST_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"


def fetch_full_nse_symbol_list():
    """NSE's own public equity-list CSV - unlike their live quote/options API
    (which 403s on scripted requests), this static archive file isn't behind
    the same anti-bot wall. Filtered to SERIES == EQ (regular, freely-traded
    mainboard equity) - BE/BZ series are trade-for-trade/surveillance-flagged
    stocks, not what a "top pick" scanner should be suggesting. Falls back to
    the curated NSE_SYMBOLS list above if the fetch fails, so a network
    hiccup at startup doesn't leave symbol search or the daily scan empty."""
    try:
        response = requests.get(NSE_EQUITY_LIST_URL, timeout=20)
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.text))
        symbols = [
            (row["SYMBOL"].strip(), row["NAME OF COMPANY"].strip())
            for row in reader
            if row.get("SYMBOL") and row.get(" SERIES", "").strip() == "EQ"
        ]
        if not symbols:
            raise ValueError("Parsed 0 symbols from NSE's equity list")
        return symbols
    except Exception as exc:
        print(f"Could not fetch the full NSE symbol list, falling back to the curated {len(NSE_SYMBOLS)}-symbol list: {exc}")
        return NSE_SYMBOLS


FULL_NSE_SYMBOLS = fetch_full_nse_symbol_list()
SYMBOL_TO_NAME = {symbol: name for symbol, name in FULL_NSE_SYMBOLS}

TOP_PICKS_UNIVERSE = [s[0] for s in NSE_SYMBOLS]
TOP_PICKS_PER_SECTOR = 10
# Minimum average daily traded value (price x average volume, in Rs) for a
# symbol to be eligible as a pick at all - expanding the scan universe to the
# full ~2,300-symbol NSE list surfaced plenty of technically-strong-looking
# but paper-thin small caps that are hard to actually get in/out of. Tried to
# source NSE's real official F&O-eligible-securities list first (their
# fo_mktlots.csv) so this could be an authoritative check rather than a
# heuristic, but every URL for it either 404s or times out from here - this
# threshold is a tunable stand-in, not an official rule. Rs 5 crore/day is a
# rough "not paper-thin" bar - well below large-cap volumes but above what a
# stock trading a few lakhs a day would clear.
MIN_DAILY_TRADED_VALUE_RS = 50_000_000
TOP_PICKS_CACHE_SECONDS = 120  # how often the UI-facing scan refreshes while markets are open
MARKET_CLOSED_CACHE_SECONDS = 1800  # nothing changes overnight/weekends - stop re-scanning every 2 min anyway
PRICE_HISTORY_PERSIST_INTERVAL_SECONDS = 900  # how often a scan actually gets written to price_history
_market_scan_cache = {"data": [], "active_timeframe": "DELIVERY", "computed_at": None}
_last_price_history_persist_at = None


def evaluate_symbol_full(symbol, nifty_is_positive, active_timeframe):
    """Mirrors build_price_prediction's active-timeframe branch exactly (same
    history window, same sentiment input) so a stock's scan numbers always
    match what its detail modal shows for the same timeframe. Evaluated once
    per symbol regardless of direction - RISE/Fall/CALL/PUT views all filter
    this same pass instead of each re-scanning the market themselves."""
    try:
        query_symbol = f"{symbol}.NS"
        stock = market_data.get_ticker(query_symbol)
        info = market_data.get_info(query_symbol)
        current_price = info.get("currentPrice", info.get("regularMarketPrice", 0))
        prev_close = info.get("previousClose", 0)
        if not current_price or not prev_close:
            return None

        # Prefer a smoothed average over today's raw volume - a single busy or
        # quiet day shouldn't flip a stock's liquidity classification.
        average_volume = info.get("averageVolume") or info.get("averageDailyVolume10Day") or info.get("volume") or info.get("regularMarketVolume") or 0
        traded_value = current_price * average_volume
        if traded_value < MIN_DAILY_TRADED_VALUE_RS:
            return None

        if active_timeframe == "INTRADAY":
            history = market_data.get_history(query_symbol, "5d", "5m")
        else:
            history = market_data.get_history(query_symbol, "3mo", "1d")

        sentiment_score = get_cached_news_sentiment(stock)["score"]
        prediction = build_algo_prediction(history, current_price, prev_close, nifty_is_positive, active_timeframe, sentiment_score)

        return {
            "symbol": symbol,
            "sector": info.get("sector") or "Other",
            "current_price": round(current_price, 2),
            "open_price": round(info.get("open") or current_price, 2),
            "high_price": round(info.get("dayHigh") or current_price, 2),
            "low_price": round(info.get("dayLow") or current_price, 2),
            "volume": info.get("volume") or info.get("regularMarketVolume") or 0,
            "average_volume": average_volume,
            "traded_value": round(traded_value, 2),
            "percent_change": round((current_price - prev_close) / prev_close * 100, 2) if prev_close else 0,
            "direction": prediction["direction"],
            "target_price": prediction["target_price"],
            "expected_change_percent": prediction["expected_change_percent"],
            "confidence_percent": prediction["confidence_percent"],
            "rise_probability": prediction["rise_probability"],
        }
    except Exception:
        return None


def persist_price_snapshots(results):
    """Writes one OHLCV row per scanned symbol - reuses data the scan already
    fetched, so this costs a DB write, not a new yfinance call. A DB hiccup
    here shouldn't break the scan itself, so it's isolated in its own
    try/except rather than bubbling up to compute_market_scan's caller."""
    if not results:
        return
    now = datetime.datetime.utcnow()
    db = SessionLocal()
    try:
        for item in results:
            db.add(PriceHistoryDB(
                symbol=item["symbol"],
                recorded_at=now,
                open=item.get("open_price"),
                high=item.get("high_price"),
                low=item.get("low_price"),
                close=item.get("current_price"),
                volume=item.get("volume"),
            ))
        db.commit()
    except Exception as exc:
        print(f"Price history snapshot failed: {exc}")
        db.rollback()
    finally:
        db.close()


def compute_market_scan(universe):
    try:
        nifty_info = market_data.get_info("^NSEI")
        nifty_current = nifty_info.get("regularMarketPrice", nifty_info.get("currentPrice", 0))
        nifty_prev = nifty_info.get("previousClose", 0)
        nifty_is_positive = (nifty_current - nifty_prev) >= 0
    except Exception:
        nifty_is_positive = True

    active_timeframe, _ = get_market_phase()

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [
            executor.submit(evaluate_symbol_full, symbol, nifty_is_positive, active_timeframe)
            for symbol in universe
        ]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result: results.append(result)

    # The UI-facing scan itself can refresh every couple minutes, but that's
    # far more often than a permanent historical row is worth writing - gate
    # persistence to its own, much coarser interval.
    global _last_price_history_persist_at
    now = datetime.datetime.utcnow()
    if _last_price_history_persist_at is None or (now - _last_price_history_persist_at).total_seconds() >= PRICE_HISTORY_PERSIST_INTERVAL_SECONDS:
        persist_price_snapshots(results)
        _last_price_history_persist_at = now

    return results, active_timeframe


def get_market_scan():
    now = datetime.datetime.utcnow()
    cache = _market_scan_cache
    cached_at = cache["computed_at"]
    current_phase, _ = get_market_phase()
    # The INTRADAY/DELIVERY algorithm itself flips at the market-close boundary,
    # not just the price data - a cache held from just before close would keep
    # showing an INTRADAY-mode read (different confidence ceiling, different
    # target) for up to effective_ttl after the switch. Force an immediate
    # recompute the moment the active phase changes, on top of the normal TTL.
    phase_changed = cached_at is not None and cache["active_timeframe"] != current_phase
    # Outside market hours nothing can have changed, so a stale cache is kept
    # much longer instead of re-scanning (and re-hitting yfinance for 150+
    # symbols) every 2 minutes all night and on weekends for no new data.
    effective_ttl = TOP_PICKS_CACHE_SECONDS if is_market_open_now() else MARKET_CLOSED_CACHE_SECONDS
    if cached_at is None or phase_changed or (now - cached_at).total_seconds() > effective_ttl:
        data, active_timeframe = compute_market_scan(TOP_PICKS_UNIVERSE)
        cache["data"] = data
        cache["active_timeframe"] = active_timeframe
        cache["computed_at"] = now
    return cache["data"], cache["active_timeframe"], cache["computed_at"]


# --- DAILY TOP PICKS/FALLS/F&O (a stable "call of the day" over the full NSE
# universe, not a live feed re-ranking a curated 128-symbol shortlist every 2
# minutes) ---
DAILY_SCAN_UNIVERSE = [s[0] for s in FULL_NSE_SYMBOLS]
_daily_scan_cache = {"date": None, "data": [], "active_timeframe": "DELIVERY", "computed_at": None}


def get_daily_market_scan():
    """Scans the full ~2,300-symbol NSE universe once per trading day and
    holds that result until the date changes, instead of re-ranking a
    128-symbol shortlist every 2 minutes. That's ~2,300 yfinance calls once a
    day rather than every 2 minutes, comfortably inside rate limits, and the
    picks genuinely cover the whole market instead of a pre-picked handful of
    large caps. The frequent small-universe scan above keeps running
    independently - it exists to feed price_history snapshots throughout the
    day, a separate concern from "what's today's top pick"."""
    ist_date = (datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)).date()
    ist_today = ist_date.isoformat()
    if _daily_scan_cache["date"] != ist_today:
        data, active_timeframe = compute_market_scan(DAILY_SCAN_UNIVERSE)
        _daily_scan_cache["date"] = ist_today
        _daily_scan_cache["data"] = data
        _daily_scan_cache["active_timeframe"] = active_timeframe
        _daily_scan_cache["computed_at"] = datetime.datetime.utcnow()
        _persist_prediction_runs(data, active_timeframe, ist_date)
    return _daily_scan_cache["data"], _daily_scan_cache["active_timeframe"], _daily_scan_cache["computed_at"]


def _persist_prediction_runs(results, active_timeframe, ist_date):
    """One immutable prediction_runs row per scanned symbol, written once a
    day right after the full-universe scan completes - the dataset the
    deferred backtesting/ranking-rework work will read from. Isolated in its
    own try/except: a DB hiccup here must never block Top Picks/Falls/F&O
    from rendering, the same reasoning as persist_price_snapshots above."""
    db = SessionLocal()
    try:
        inserted = record_daily_predictions(db, results, active_timeframe, ist_date)
        print(f"prediction_runs: recorded {inserted} new rows for {ist_date}")
    except Exception as exc:
        print(f"prediction_runs: recording failed for {ist_date}: {exc}")
    finally:
        db.close()


def get_direction_scan(wanted_direction):
    """Top Picks, Top Falls, and F&O all rank the same way: filtered to one
    direction, then ordered by traded value (most liquid first), not by
    expected move. A stock's predicted % move is still what puts it in the
    RISE/FALL bucket at all - liquidity only decides the order within that
    bucket. Real NSE F&O eligibility is gated on liquidity/market-wide
    position limits, not on which stock has the flashiest predicted move, and
    a "top pick" nobody can actually get in and out of easily isn't much of
    a pick."""
    all_results, active_timeframe, computed_at = get_daily_market_scan()
    filtered = [r for r in all_results if r["direction"] == wanted_direction]
    filtered.sort(key=lambda item: item["traded_value"], reverse=True)
    return filtered, active_timeframe, computed_at
