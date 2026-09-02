from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from contextlib import asynccontextmanager
from typing import Literal
import asyncio
import yfinance as yf
import requests
import jwt
import datetime
import bcrypt
import csv
import io
import concurrent.futures
from news_pipeline import sentiment as news_sentiment
from news_pipeline import pipeline as news_pipeline
from news_pipeline import normalize as news_normalize
from news_pipeline import worker as news_worker
from news_pipeline import config as news_config

# --- CONFIGURATION ---
DATABASE_URL = "postgresql://postgres:password@localhost:5432/stockdemo"
TELEGRAM_BOT_TOKEN = "8983513593:AAGA1eA8S-YXHshCgYdivdMdijl_MJkdgEs"
TELEGRAM_CHAT_ID = "1425739939"
# Free key from ipoguru.in (email ipoguru.in@gmail.com to request one) - the
# IPO tab shows a "not configured" state until this is filled in.
IPO_GURU_API_KEY = ""
SECRET_KEY = "my-awesome-demo-key-198107"
ALGORITHM = "HS256"
# Manually maintained macro reference (RBI has no simple free live-data API) - update when RBI moves the rate.
RBI_REPO_RATE = {"value_percent": 5.5, "last_updated": "2026-06-06", "note": "Manually maintained reference, not a live feed."}

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

# --- ALGORITHM PREDICTION LOGIC ---
def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))

def get_market_phase():
    ist_now = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    market_open = ist_now.replace(hour=9, minute=15, second=0, microsecond=0)
    delivery_switch = ist_now.replace(hour=15, minute=25, second=0, microsecond=0)
    market_close = ist_now.replace(hour=15, minute=30, second=0, microsecond=0)

    if market_open <= ist_now < delivery_switch:
        return "INTRADAY", "Intraday algorithm active until 3:25 PM IST."
    if delivery_switch <= ist_now <= market_close:
        return "DELIVERY", "Delivery algorithm active for the final 5 minutes before close."
    return "DELIVERY", "Market is outside regular intraday hours; delivery algorithm is active."

def is_market_open_now():
    """Unlike get_market_phase (which always returns an active algorithm
    choice even when the market's shut), this is a plain yes/no used to gate
    background scanning - no point re-fetching yfinance every 2 minutes
    overnight or on weekends when the price cannot have changed."""
    ist_now = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    if ist_now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    market_open = ist_now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = ist_now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= ist_now <= market_close

def empty_algo_prediction(current_price, timeframe, summary):
    return {
        "timeframe": timeframe,
        "direction": "SIDEWAYS",
        "rise_probability": 50,
        "fall_probability": 50,
        "target_price": round(current_price, 2),
        "expected_change_percent": 0,
        "support": round(current_price, 2),
        "resistance": round(current_price, 2),
        "confidence": "Low",
        "summary": summary,
    }

def build_algo_prediction(history, current_price, previous_close, nifty_is_positive, timeframe, sentiment_score=0):
    default_prediction = empty_algo_prediction(
        current_price,
        timeframe,
        f"Not enough {timeframe.lower()} candle history for a strong forecast.",
    )

    if history is None or history.empty or len(history) < 8: return default_prediction
    clean_history = history.dropna(subset=["Open", "High", "Low", "Close"])
    if len(clean_history) < 8: return default_prediction

    closes = clean_history["Close"]
    returns = closes.pct_change().dropna()
    if returns.empty: return default_prediction

    fast_window = 3 if timeframe == "INTRADAY" else 5
    slow_window = 9 if timeframe == "INTRADAY" else 20
    lookback = min(slow_window, len(closes) - 1)

    fast_avg = float(closes.tail(fast_window).mean())
    slow_avg = float(closes.tail(slow_window).mean()) if len(closes) >= slow_window else float(closes.mean())
    momentum = (float(closes.iloc[-1]) - float(closes.iloc[-lookback - 1])) / float(closes.iloc[-lookback - 1])
    recent_candles = clean_history.tail(fast_window + 2)
    green_candles = int((recent_candles["Close"] > recent_candles["Open"]).sum())
    last_candle = clean_history.iloc[-1]
    last_range = float(last_candle["High"] - last_candle["Low"])
    candle_body = 0 if last_range == 0 else float(last_candle["Close"] - last_candle["Open"]) / last_range
    avg_abs_move = float(returns.tail(slow_window).abs().mean())
    volatility = float(returns.tail(slow_window).std()) if len(returns) >= 2 else avg_abs_move

    score = 0
    score += clamp(momentum * (900 if timeframe == "INTRADAY" else 500), -20, 20)
    score += 10 if fast_avg >= slow_avg else -10
    score += 7 if current_price >= previous_close else -7
    score += 5 if nifty_is_positive else -5
    score += (green_candles - (len(recent_candles) / 2)) * 2
    score += clamp(candle_body * 10, -10, 10)
    score += clamp(sentiment_score * (1.4 if timeframe == "INTRADAY" else 1.0), -12, 12)

    rise_probability = round(clamp(50 + score, 12, 88))
    fall_probability = 100 - rise_probability
    direction = "RISE" if rise_probability > 55 else "FALL" if fall_probability > 55 else "SIDEWAYS"

    max_expected_move = 0.018 if timeframe == "INTRADAY" else 0.08
    min_expected_move = 0.002 if timeframe == "INTRADAY" else 0.006
    expected_move = clamp(avg_abs_move + (abs(score) / 1500), min_expected_move, max_expected_move)
    expected_change_percent = expected_move * 100

    if direction == "FALL":
        target_price = current_price * (1 - expected_move)
        expected_change_percent *= -1
    elif direction == "SIDEWAYS":
        target_price = current_price
        expected_change_percent = 0
    else:
        target_price = current_price * (1 + expected_move)

    confidence = "High" if abs(score) >= 24 and volatility < max_expected_move else "Medium" if abs(score) >= 13 else "Low"
    confidence_percent = round(clamp(50 + abs(score) * 1.4, 50, 92))
    if not (volatility < max_expected_move):
        confidence_percent = min(confidence_percent, 78)  # volatility disqualifies a "High" read
    support = float(clean_history["Low"].tail(slow_window).min())
    resistance = float(clean_history["High"].tail(slow_window).max())
    summary = (f"{timeframe.title()} bias from recent candles, fast/slow MA, momentum, volatility, previous close, and Nifty.")

    return {
        "timeframe": timeframe, "direction": direction, "rise_probability": rise_probability,
        "fall_probability": fall_probability, "target_price": round(target_price, 2),
        "expected_change_percent": round(expected_change_percent, 2), "support": round(support, 2),
        "resistance": round(resistance, 2), "confidence": confidence, "confidence_percent": confidence_percent,
        "summary": summary,
    }

def empty_news_sentiment(note="No recent news found for this symbol."):
    """Shared shape for "nothing to analyze" - used whenever a news fetch
    comes back empty, so every caller (stock detail, market scan, IPO cards)
    renders the same honest "no data" state instead of each inventing one."""
    return {"score": 0, "label": "Neutral", "headlines": [], "note": note}

def score_headlines(headlines: list[str]):
    """Scores headline titles via the news_pipeline's Tier-0 financial-lexicon
    classifier (negation-scope + contrast-clause + magnitude-aware - see
    news_pipeline/sentiment.py) instead of plain buzzword counting. Same
    signature/return shape as before this replacement, so every existing
    caller (stock detail, the once-daily full-universe scan, IPO cards) keeps
    working unmodified. Pure function of the headline text - decoupled from
    however the caller fetched those headlines (a Ticker's news feed, a
    free-text Search, or anything else). Never escalates to the optional
    Tier-2 LLM classifier, so this stays free/instant regardless of caller -
    that's what makes it safe for the ~2,300-symbol daily scan."""
    if not headlines:
        return empty_news_sentiment()
    return news_sentiment.classify_headlines(headlines)

def extract_headline_title(article):
    """Yahoo's news article dicts show up in more than one shape depending on
    the endpoint - sometimes a top-level "title", sometimes nested under
    "content" - so check both rather than assuming one."""
    if not isinstance(article, dict): return None
    content = article.get("content")
    title = content.get("title") if isinstance(content, dict) else None
    if not title: title = article.get("title")
    return str(title) if title else None

def analyze_news_sentiment(stock):
    """Extracts headline titles off a yfinance Ticker's news feed, then hands
    them to score_headlines for the actual scoring."""
    try:
        articles = stock.get_news(count=8) or []
    except Exception:
        return empty_news_sentiment()

    headlines = [title for article in articles if (title := extract_headline_title(article))]
    return score_headlines(headlines)

NEWS_SENTIMENT_CACHE_SECONDS = 600  # news moves slower than price - 10 min keeps it from flip-flopping every request
_news_sentiment_cache = {}

def get_cached_news_sentiment(stock):
    """Same sentiment analysis, but shared across every caller for a symbol
    (the detail endpoint, the market scan) instead of each re-fetching Yahoo's
    news feed independently - that duplicate, uncached fetching was the actual
    cause of the sentiment score changing on every single request."""
    symbol = stock.ticker
    now = datetime.datetime.utcnow()
    cached = _news_sentiment_cache.get(symbol)
    if cached and (now - cached["computed_at"]).total_seconds() < NEWS_SENTIMENT_CACHE_SECONDS:
        return cached["data"]

    result = analyze_news_sentiment(stock)
    _news_sentiment_cache[symbol] = {"data": result, "computed_at": now}
    return result

def build_rich_news_sentiment(stock, symbol, company_name, sector):
    """The on-demand (single stock detail page) sentiment read: same legacy
    shape ({score, label, headlines, note}) as get_cached_news_sentiment,
    but score/label/note now reflect the news_pipeline's relevance-filtered,
    deduplicated, source/recency/novelty-weighted aggregate instead of a flat
    scan of today's headlines - with the richer breakdown (confidence,
    event counts, top events, 1h/6h/24h/7d windows, momentum) merged in
    additively for a future NewsPanel to use. Falls back to the plain legacy
    shape on any pipeline error - a stock detail page should never blank out
    over this. Only this on-demand path and IPO lookups ever pass
    allow_llm_escalation=True; the once-daily full-universe scan never
    reaches this function at all (it stays on get_cached_news_sentiment)."""
    legacy = get_cached_news_sentiment(stock)
    try:
        def fetch_raw_articles():
            return news_normalize.normalize_yfinance_articles(stock.get_news(count=8) or [], source="yfinance_ticker")

        db = SessionLocal()
        try:
            rich = news_pipeline.get_or_refresh_stock_sentiment(
                db, symbol.upper(), company_name, sector, fetch_raw_articles, allow_llm_escalation=True,
            )
        finally:
            db.close()
    except Exception as exc:
        print(f"news_pipeline: rich sentiment failed for {symbol}, falling back to legacy scan: {exc}")
        return legacy

    merged = dict(legacy)
    if rich["reason"] is None:
        merged["score"] = rich["legacy_score"]
        if legacy["label"] != "Mixed":
            merged["label"] = "Positive" if rich["legacy_score"] > 2 else "Negative" if rich["legacy_score"] < -2 else "Neutral"
        merged["note"] = (
            f"{rich['label']} news environment (score {rich['score']:+.0f}/100, confidence {rich['confidence']:.0%}) "
            f"across {rich['unique_event_count']} distinct event(s) from {rich['article_count']} article(s) in the last 24h."
        )
    merged.update({
        "confidence": rich["confidence"], "band_label": rich["label"], "raw_score": rich["score"],
        "article_count": rich["article_count"], "unique_event_count": rich["unique_event_count"],
        "positive_events": rich["positive_events"], "negative_events": rich["negative_events"],
        "neutral_events": rich["neutral_events"], "top_events": rich["top_events"],
        "windows": rich["windows"], "momentum": rich["momentum"], "reason": rich["reason"],
        "computed_at": rich["computed_at"],
    })
    return merged

def build_close_open_forecast(delivery_history, current_price, previous_close, sentiment_score):
    """Estimates today's close and tomorrow's open from daily momentum, moving
    averages, previous close, news sentiment, and the historical overnight
    open/close gap - separate from the intraday/delivery panels above since
    those reason in percent-move terms, not a specific close/open price."""
    ist_today = (datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)).date()
    next_trading_day = ist_today + datetime.timedelta(days=1)
    while next_trading_day.weekday() >= 5:  # Saturday=5, Sunday=6 - skip weekends
        next_trading_day += datetime.timedelta(days=1)
    close_date = ist_today.isoformat()
    next_open_date = next_trading_day.isoformat()

    default = {
        "predicted_close_today": round(current_price, 2),
        "predicted_open_tomorrow": round(current_price, 2),
        "close_change_percent": 0,
        "open_change_percent": 0,
        "confidence_percent": 50,
        "close_date": close_date,
        "next_open_date": next_open_date,
        "rationale": "Not enough daily history to forecast a close/open price.",
    }
    if delivery_history is None or delivery_history.empty or len(delivery_history) < 10:
        return default
    clean = delivery_history.dropna(subset=["Open", "High", "Low", "Close"])
    if len(clean) < 10:
        return default

    closes = clean["Close"]
    opens = clean["Open"]
    fast_avg = float(closes.tail(5).mean())
    slow_avg = float(closes.tail(20).mean()) if len(closes) >= 20 else float(closes.mean())
    lookback = min(20, len(closes) - 1)
    momentum = (float(closes.iloc[-1]) - float(closes.iloc[-lookback - 1])) / float(closes.iloc[-lookback - 1])

    overnight_gaps = (opens.iloc[1:].to_numpy() - closes.iloc[:-1].to_numpy()) / closes.iloc[:-1].to_numpy()
    recent_gaps = overnight_gaps[-20:]
    avg_gap_pct = float(recent_gaps.mean()) if len(recent_gaps) else 0.0

    score = 0
    score += clamp(momentum * 500, -20, 20)
    score += 8 if fast_avg >= slow_avg else -8
    score += 6 if current_price >= previous_close else -6
    score += clamp(sentiment_score * 1.2, -15, 15)

    ist_now = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    market_open = ist_now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = ist_now.replace(hour=15, minute=30, second=0, microsecond=0)
    total_minutes = (market_close - market_open).total_seconds() / 60
    elapsed_minutes = (ist_now - market_open).total_seconds() / 60
    elapsed_fraction = clamp(elapsed_minutes / total_minutes, 0, 1) if total_minutes else 1

    expected_move = clamp(abs(score) / 1800, 0.002, 0.05)
    directional_target = current_price * (1 + expected_move) if score >= 0 else current_price * (1 - expected_move)

    # Early in the session the close leans toward the directional target; by
    # market close it converges to the current (= closing) price.
    predicted_close_today = current_price * elapsed_fraction + directional_target * (1 - elapsed_fraction)
    gap_bias = clamp(score / 2500, -0.015, 0.015)
    predicted_open_tomorrow = predicted_close_today * (1 + avg_gap_pct + gap_bias)

    confidence_percent = round(clamp(50 + abs(score) * 1.4, 50, 95))
    sentiment_word = "positive" if sentiment_score > 0 else "negative" if sentiment_score < 0 else "neutral"
    direction_word = "higher" if score >= 0 else "lower"
    rationale = (
        f"Blends daily momentum, moving averages, previous close, and {sentiment_word} news sentiment to "
        f"lean {direction_word}; overnight gap uses the {len(recent_gaps)}-day average open-vs-prior-close jump."
    )

    return {
        "predicted_close_today": round(predicted_close_today, 2),
        "predicted_open_tomorrow": round(predicted_open_tomorrow, 2),
        "close_change_percent": round((predicted_close_today - current_price) / current_price * 100, 2) if current_price else 0,
        "open_change_percent": round((predicted_open_tomorrow - predicted_close_today) / predicted_close_today * 100, 2) if predicted_close_today else 0,
        "confidence_percent": confidence_percent,
        "close_date": close_date,
        "next_open_date": next_open_date,
        "rationale": rationale,
    }

def build_fundamentals(stock_info):
    """Valuation/growth markers experts check alongside price action. Pulled
    straight from yfinance's info payload, which is Yahoo's own last-reported
    figures - fields come back None when a stock doesn't report them."""
    def pct(value):
        if not isinstance(value, (int, float)): return None
        # yfinance sometimes reports these as a decimal fraction (0.12) and
        # sometimes already as a percent (12.0) depending on the field/version.
        return round(value, 2) if abs(value) > 1 else round(value * 100, 2)

    return {
        "trailing_pe": round(stock_info.get("trailingPE"), 2) if isinstance(stock_info.get("trailingPE"), (int, float)) else None,
        "forward_pe": round(stock_info.get("forwardPE"), 2) if isinstance(stock_info.get("forwardPE"), (int, float)) else None,
        "eps_ttm": stock_info.get("trailingEps"),
        "price_to_book": round(stock_info.get("priceToBook"), 2) if isinstance(stock_info.get("priceToBook"), (int, float)) else None,
        "book_value": stock_info.get("bookValue"),
        "revenue_growth_yoy_percent": pct(stock_info.get("revenueGrowth")),
        "earnings_growth_yoy_percent": pct(stock_info.get("earningsGrowth")),
        "earnings_growth_qoq_percent": pct(stock_info.get("earningsQuarterlyGrowth")),
        "revenue_growth_qoq_percent": pct(stock_info.get("revenueQuarterlyGrowth")),
        "dividend_yield_percent": pct(stock_info.get("dividendYield")),
        "market_cap": stock_info.get("marketCap"),
        "beta": stock_info.get("beta"),
        "week52_high": stock_info.get("fiftyTwoWeekHigh"),
        "week52_low": stock_info.get("fiftyTwoWeekLow"),
        "sector": stock_info.get("sector"),
        "industry": stock_info.get("industry"),
        "rbi_repo_rate": RBI_REPO_RATE,
    }

def build_price_prediction(stock, current_price, previous_close, nifty_is_positive, symbol, company_name, sector):
    default_prediction = {
        "active": "DELIVERY", "market_phase": "Unable to determine market phase.",
        "intraday": empty_algo_prediction(current_price, "INTRADAY", "Intraday data unavailable."),
        "delivery": empty_algo_prediction(current_price, "DELIVERY", "Delivery data unavailable."),
        "news": empty_news_sentiment(),
        "forecast": build_close_open_forecast(None, current_price, previous_close, 0),
    }
    try:
        active, market_phase = get_market_phase()
        intraday_history = stock.history(period="5d", interval="5m", auto_adjust=False)
        delivery_history = stock.history(period="3mo", interval="1d", auto_adjust=False)
        news = build_rich_news_sentiment(stock, symbol, company_name, sector)
        sentiment_score = news["score"]
        return {
            "active": active, "market_phase": market_phase,
            "intraday": build_algo_prediction(intraday_history, current_price, previous_close, nifty_is_positive, "INTRADAY", sentiment_score),
            "delivery": build_algo_prediction(delivery_history, current_price, previous_close, nifty_is_positive, "DELIVERY", sentiment_score),
            "news": news,
            "forecast": build_close_open_forecast(delivery_history, current_price, previous_close, sentiment_score),
        }
    except Exception:
        return default_prediction

# --- CANDLESTICK CHART DATA (Google-Finance-style range selector) ---
CANDLE_RANGES = {
    "1D": {"period": "1d", "interval": "5m"},
    "5D": {"period": "5d", "interval": "15m"},
    "1M": {"period": "1mo", "interval": "1d"},
    "6M": {"period": "6mo", "interval": "1d"},
    "1Y": {"period": "1y", "interval": "1d"},
    "5Y": {"period": "5y", "interval": "1wk"},
    "MAX": {"period": "max", "interval": "1mo"},
}

def build_candles(stock, range_key):
    config = CANDLE_RANGES.get(range_key, CANDLE_RANGES["1M"])
    history = stock.history(period=config["period"], interval=config["interval"], auto_adjust=False)
    if history is None or history.empty:
        return []

    clean = history.dropna(subset=["Open", "High", "Low", "Close"])
    candles = []
    for timestamp, row in clean.iterrows():
        volume = row.get("Volume", 0)
        candles.append({
            "time": int(timestamp.timestamp()),
            "open": round(float(row["Open"]), 2),
            "high": round(float(row["High"]), 2),
            "low": round(float(row["Low"]), 2),
            "close": round(float(row["Close"]), 2),
            "volume": int(volume) if volume == volume else 0,  # NaN != NaN
        })
    return candles

# --- TOP INTRADAY PICKS (scans the full NSE directory, ranks by expected same-day move, grouped by sector) ---
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
        stock = yf.Ticker(f"{symbol}.NS")
        info = stock.info
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
            history = stock.history(period="5d", interval="5m", auto_adjust=False)
        else:
            history = stock.history(period="3mo", interval="1d", auto_adjust=False)

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
        nifty_info = yf.Ticker("^NSEI").info
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
    ist_today = (datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)).date().isoformat()
    if _daily_scan_cache["date"] != ist_today:
        data, active_timeframe = compute_market_scan(DAILY_SCAN_UNIVERSE)
        _daily_scan_cache["date"] = ist_today
        _daily_scan_cache["data"] = data
        _daily_scan_cache["active_timeframe"] = active_timeframe
        _daily_scan_cache["computed_at"] = datetime.datetime.utcnow()
    return _daily_scan_cache["data"], _daily_scan_cache["active_timeframe"], _daily_scan_cache["computed_at"]

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

# --- DATABASE SETUP ---
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    phone_number = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    notification_preference = Column(String, nullable=True)  # "email" | "whatsapp" | "telegram"

    alert_rules = relationship("AlertRuleDB", back_populates="owner", cascade="all, delete-orphan")

class AlertRuleDB(Base):
    """Threshold price alerts - this table has always been alerting, not a
    plain watchlist, hence the name (the table itself stays "watchlists" so
    no data migration is needed for the rename)."""
    __tablename__ = "watchlists"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    group_id = Column(Integer, ForeignKey("stock_groups.id"), nullable=True)
    symbol = Column(String, index=True)
    upper_threshold = Column(Float, nullable=True)
    lower_threshold = Column(Float, nullable=True)
    alert_triggered = Column(Integer, default=0)

    owner = relationship("UserDB", back_populates="alert_rules")

class StockGroupDB(Base):
    """User-created named folders (e.g. "Banking", "My Picks") for organizing
    tracked stocks/alerts - shared by both the Watchlist and Alerts pages,
    distinguished by group_type. Capped at 10 per user per type, enforced at
    the endpoint (count-then-insert; fine since this is a single-user action,
    not concurrent - not worth a SELECT FOR UPDATE)."""
    __tablename__ = "stock_groups"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    group_type = Column(String, index=True)  # "watchlist" | "alert"
    name = Column(String)

class TrackedStockDB(Base):
    """Plain watchlist entry - just a symbol to keep an eye on, no threshold."""
    __tablename__ = "tracked_stocks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    group_id = Column(Integer, ForeignKey("stock_groups.id"), nullable=True)
    symbol = Column(String, index=True)

class PriceHistoryDB(Base):
    """Our own OHLCV snapshots, saved every market-scan cycle for the whole
    NSE_SYMBOLS universe - piggybacks on data the scan already fetches, so it
    costs no extra yfinance calls. Gives us a durable, app-owned dataset to
    backtest against or eventually train a model on, instead of only ever
    trusting whatever yfinance returns live in the moment."""
    __tablename__ = "price_history"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    recorded_at = Column(DateTime, index=True)
    open = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=True)
    volume = Column(Integer, nullable=True)

Base.metadata.create_all(bind=engine)

from news_pipeline.models import NewsBase
NewsBase.metadata.create_all(bind=engine)

def run_startup_migrations():
    """Best-effort ALTER TABLE for pre-existing Postgres databases.

    Base.metadata.create_all() only creates missing tables — it never adds
    columns/constraints to a table that already exists, so new user profile
    fields and the watchlist->user foreign key need to be patched in by hand.
    """
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS age INTEGER",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS gender VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS notification_preference VARCHAR",
        """
        DO $$ BEGIN
            ALTER TABLE watchlists ADD CONSTRAINT fk_watchlists_user
                FOREIGN KEY (user_id) REFERENCES users(id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """,
        # group_id is new - Base.metadata.create_all() never alters an existing
        # table, so the column and its FK need the same manual treatment. Safe
        # on live data: a nullable column addition is metadata-only on Postgres
        # 11+, and FK constraints never validate against NULLs, so every
        # pre-existing alert row just gets group_id = NULL (shows up under "All").
        "ALTER TABLE watchlists ADD COLUMN IF NOT EXISTS group_id INTEGER",
        """
        DO $$ BEGIN
            ALTER TABLE watchlists ADD CONSTRAINT fk_watchlists_group
                FOREIGN KEY (group_id) REFERENCES stock_groups(id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """,
    ]
    # Each statement runs in its own transaction so one failure (e.g. a
    # pre-existing FK violation from orphaned rows) can't roll back the
    # others, such as the plain column additions.
    for statement in statements:
        try:
            with engine.begin() as conn:
                conn.execute(text(statement))
        except Exception as exc:
            print(f"Startup migration statement skipped/failed: {exc}")

run_startup_migrations()

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- PROACTIVE ALERT BACKGROUND TASK ---
def send_telegram_message(text: str):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
    )

async def proactive_price_checker():
    while True:
        await asyncio.sleep(60)
        db = SessionLocal()
        try:
            active_alerts = db.query(AlertRuleDB).filter(AlertRuleDB.alert_triggered == 0).all()
            if not active_alerts: continue

            for item in active_alerts:
                try:
                    query_symbol = f"{item.symbol.upper()}.NS" if not item.symbol.upper().endswith('.NS') else item.symbol.upper()
                    stock = yf.Ticker(query_symbol)
                    price = stock.info.get('currentPrice', stock.info.get('regularMarketPrice', 0))
                    if price == 0: continue

                    user = db.query(UserDB).filter(UserDB.id == item.user_id).first()
                    alert_msg = None

                    if item.upper_threshold and price >= item.upper_threshold:
                        alert_msg = f"🚀 *TARGET HIT: {item.symbol}* 🚀\nUser: {user.username}\nPrice crossed above your ₹{item.upper_threshold} target!\n*Current Price: ₹{price}*"
                    elif item.lower_threshold and price <= item.lower_threshold:
                        alert_msg = f"📉 *STOP LOSS ALERT: {item.symbol}* 📉\nUser: {user.username}\nPrice dropped below your ₹{item.lower_threshold} target!\n*Current Price: ₹{price}*"

                    if alert_msg:
                        send_telegram_message(alert_msg)
                        item.alert_triggered = 1
                        db.commit()
                except Exception as e:
                    print(f"Error checking {item.symbol}: {e}")
        finally:
            db.close()

async def market_scan_warmer():
    """Keeps the small curated-universe scan warm on a loop. Top Picks/Falls/
    F&O no longer read from this - they use the once-a-day full-universe scan
    below. This one now exists purely to (a) feed price_history snapshots
    throughout the day and (b) give symbol search a warm quote_lookup from
    startup. Only actually scans during market hours - outside that window
    the price can't have changed, so there's nothing worth re-fetching for."""
    while True:
        if is_market_open_now():
            try:
                await asyncio.to_thread(get_market_scan)
            except Exception as exc:
                print(f"Market scan warm-up failed: {exc}")
        await asyncio.sleep(TOP_PICKS_CACHE_SECONDS)

async def daily_scan_warmer():
    """Proactively computes the once-a-day full-universe scan in the
    background, so the first person to open Top Picks/Falls/F&O each day
    isn't the one stuck waiting through a ~2,300-symbol sweep. get_daily_
    market_scan() itself is a no-op once today's result is already cached,
    so checking every 10 min here just catches the moment a new trading day
    starts without needing a precise scheduled trigger."""
    while True:
        if is_market_open_now():
            try:
                await asyncio.to_thread(get_daily_market_scan)
            except Exception as exc:
                print(f"Daily scan warm-up failed: {exc}")
        await asyncio.sleep(600)

async def news_rss_poller():
    """Periodically ingests the 3 market-wide RSS feeds against the full NSE
    symbol directory. Runs independent of market hours - macro/results news
    (and the feeds themselves) doesn't stop just because trading is closed,
    unlike price. sector comes opportunistically from whatever the daily
    scan has already cached (zero extra yfinance calls) - symbols outside
    today's cached scan just get sector=None, which only costs the
    sector-wide relevance band for those symbols, not the whole match."""
    symbol_names = dict(FULL_NSE_SYMBOLS)
    while True:
        try:
            symbol_to_sector = {r["symbol"]: r.get("sector") for r in _daily_scan_cache["data"]}
            symbol_directory = [(symbol, name, symbol_to_sector.get(symbol)) for symbol, name in symbol_names.items()]
            db = SessionLocal()
            try:
                summary = await asyncio.to_thread(news_worker.poll_once, db, symbol_directory)
                print(f"news_pipeline RSS poll: {summary}")
            finally:
                db.close()
        except Exception as exc:
            print(f"news_pipeline RSS poller failed: {exc}")
        sleep_seconds = news_config.RSS_POLL_SECONDS_MARKET_OPEN if is_market_open_now() else news_config.RSS_POLL_SECONDS_MARKET_CLOSED
        await asyncio.sleep(sleep_seconds)

@asynccontextmanager
async def lifespan(app: FastAPI):
    price_checker_task = asyncio.create_task(proactive_price_checker())
    market_scan_task = asyncio.create_task(market_scan_warmer())
    daily_scan_task = asyncio.create_task(daily_scan_warmer())
    news_rss_task = asyncio.create_task(news_rss_poller())
    yield
    price_checker_task.cancel()
    market_scan_task.cancel()
    news_rss_task.cancel()
    daily_scan_task.cancel()

# --- AUTHENTICATION SETUP ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def seed_default_user():
    """Creates the admin/admin account so it can be used without signing up."""
    db = SessionLocal()
    try:
        if not db.query(UserDB).filter(UserDB.username == "admin").first():
            db.add(UserDB(
                username="admin",
                hashed_password=get_password_hash("admin"),
                full_name="Admin",
                notification_preference="email",
            ))
            db.commit()
    finally:
        db.close()

seed_default_user()

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=60)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(UserDB).filter(UserDB.username == username).first()
    if user is None: raise HTTPException(status_code=401, detail="User not found")
    return user

# --- FASTAPI APP ---
app = FastAPI(lifespan=lifespan)

@app.exception_handler(Exception)
async def catch_all_errors(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": f"THE REAL ERROR IS: {repr(exc)}"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- PYDANTIC MODELS ---
class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    age: int
    phone_number: str
    gender: str
    notification_preference: str  # "email" | "whatsapp" | "telegram"

class AlertData(BaseModel):
    symbol: str
    current_price: float
    open: float
    high: float
    low: float
    previous_close: float
    suggestion: str
    percent_change: float
    volume: int
    prediction: dict | None = None

class AlertCreate(BaseModel):
    symbol: str
    upper_threshold: float | None = None
    lower_threshold: float | None = None
    group_id: int | None = None

class AlertItemOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    symbol: str
    upper_threshold: float | None
    lower_threshold: float | None
    alert_triggered: int
    group_id: int | None

class TrackedStockCreate(BaseModel):
    symbol: str
    group_id: int | None = None

class TrackedStockOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    symbol: str
    group_id: int | None

class StockGroupCreate(BaseModel):
    group_type: Literal["watchlist", "alert"]
    name: str

class StockGroupRename(BaseModel):
    name: str

class StockGroupOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    group_type: str
    name: str

MAX_GROUPS_PER_TYPE = 10

# --- ROUTES ---
@app.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(UserDB).filter(UserDB.username == user.username).first()
    if db_user: raise HTTPException(status_code=400, detail="Username already registered")
    new_user = UserDB(
        username=user.username,
        hashed_password=get_password_hash(user.password),
        full_name=user.full_name,
        age=user.age,
        phone_number=user.phone_number,
        gender=user.gender,
        notification_preference=user.notification_preference,
    )
    db.add(new_user)
    db.commit()
    return {"message": "User created successfully"}

@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/symbols/search")
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

STOCK_DETAIL_CACHE_SECONDS = 90  # short-lived cache, same TTL-dict idiom as the rest of this file
_stock_detail_cache = {}

def _fetch_stock_data(symbol: str):
    """The actual live yfinance fetch + prediction build. Raises on any
    failure (rate-limited, bad symbol, network) - get_stock_data below is
    what decides whether that failure is fatal or falls back to a cached
    last-known-good response."""
    query_symbol = f"{symbol.upper()}.NS" if not symbol.upper().endswith('.NS') else symbol.upper()

    stock = yf.Ticker(query_symbol)
    stock_info = stock.info

    current_price = stock_info.get('currentPrice', stock_info.get('regularMarketPrice', 0))
    open_price = stock_info.get('open', 0)
    high_price = stock_info.get('dayHigh', 0)
    low_price = stock_info.get('dayLow', 0)
    prev_close = stock_info.get('previousClose', 0)
    volume = stock_info.get('volume', stock_info.get('regularMarketVolume', 0))

    percent_change = ((current_price - prev_close) / prev_close) * 100 if prev_close else 0

    nifty = yf.Ticker("^NSEI")
    nifty_info = nifty.info
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

@app.get("/api/stock/{symbol}")
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

@app.get("/api/news-sentiment/{symbol}")
def get_news_sentiment(symbol: str, current_user: UserDB = Depends(get_current_user)):
    """Standalone view of the same news_pipeline breakdown embedded in
    /api/stock/{symbol}'s prediction.news - useful on its own when a caller
    wants the full event/window/momentum detail without the price/candle/
    fundamentals payload. Same on-demand, DB-cached, LLM-escalation-eligible
    path as the stock detail page (never the once-daily full-universe scan)."""
    symbol_upper = symbol.upper()
    company_name = SYMBOL_TO_NAME.get(symbol_upper, symbol_upper)
    try:
        stock = yf.Ticker(f"{symbol_upper}.NS")
        sector = None
        try:
            sector = stock.info.get("sector")
        except Exception:
            pass

        def fetch_raw_articles():
            return news_normalize.normalize_yfinance_articles(stock.get_news(count=8) or [], source="yfinance_ticker")

        db = SessionLocal()
        try:
            breakdown = news_pipeline.get_or_refresh_stock_sentiment(
                db, symbol_upper, company_name, sector, fetch_raw_articles, allow_llm_escalation=True,
            )
        finally:
            db.close()
        return breakdown
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"News sentiment not available: {str(e)}")

@app.get("/api/stock/{symbol}/candles")
def get_stock_candles(symbol: str, range: str = Query(default="1M"), current_user: UserDB = Depends(get_current_user)):
    try:
        query_symbol = f"{symbol.upper()}.NS" if not symbol.upper().endswith('.NS') else symbol.upper()
        range_key = range.upper() if range.upper() in CANDLE_RANGES else "1M"
        stock = yf.Ticker(query_symbol)
        candles = build_candles(stock, range_key)
        return {
            "symbol": query_symbol.replace('.NS', ''),
            "range": range_key,
            "available_ranges": list(CANDLE_RANGES.keys()),
            "candles": candles,
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Candle data not found: {str(e)}")

@app.get("/api/top-picks")
def get_top_intraday_picks(direction: str = Query(default="RISE"), current_user: UserDB = Depends(get_current_user)):
    wanted_direction = "FALL" if direction.upper() == "FALL" else "RISE"
    picks, active_timeframe, computed_at = get_direction_scan(wanted_direction)

    sectors = {}
    for pick in picks:
        sectors.setdefault(pick["sector"], [])
        if len(sectors[pick["sector"]]) < TOP_PICKS_PER_SECTOR:
            sectors[pick["sector"]].append(pick)

    # Sectors ordered by their most-liquid pick too, matching the ranking
    # rule for the picks within them.
    sector_groups = [
        {"sector": sector, "picks": sector_picks}
        for sector, sector_picks in sorted(
            sectors.items(),
            key=lambda item: item[1][0]["traded_value"],
            reverse=True,
        )
    ]

    return {
        "direction": wanted_direction,
        "top_overall": picks[:10],
        "sectors": sector_groups,
        "active_timeframe": active_timeframe,
        "total_available": len(picks),
        "scanned_universe_size": len(DAILY_SCAN_UNIVERSE),
        "computed_at": computed_at.isoformat() if computed_at else None,
        "scan_cadence": "daily",
    }

FNO_DISCLAIMER = (
    "This is our own directional algorithm mapped onto options terms, not a real NSE options chain. "
    "The strike is rounded to a plausible interval, not a verified listed strike, and there is no live "
    "premium, open interest, or FII/DII short-positioning data behind it - those require a paid market "
    "data feed that this app does not have access to."
)

def suggest_option_strike(price):
    """Rounds to a plausible NSE strike interval - an approximation, not a verified listed strike."""
    if price < 50: step = 2.5
    elif price < 100: step = 5
    elif price < 500: step = 10
    elif price < 1000: step = 20
    elif price < 2500: step = 50
    else: step = 100
    return round(round(price / step) * step, 2)

def build_option_idea(pick, option_type):
    current_price = pick["current_price"]
    target_price = pick["target_price"]
    reward = abs(target_price - current_price)
    # Risk half the expected reward - a standard risk:reward heuristic, not derived from real option greeks.
    stop_loss_price = round(current_price - reward / 2, 2) if option_type == "CALL" else round(current_price + reward / 2, 2)

    return {
        "symbol": pick["symbol"],
        "sector": pick["sector"],
        "option_type": option_type,
        "current_price": current_price,
        "suggested_strike": suggest_option_strike(current_price),
        "target_underlying_price": target_price,
        "stop_loss_underlying_price": stop_loss_price,
        "expected_change_percent": pick["expected_change_percent"],
        "confidence_percent": pick["confidence_percent"],
        "traded_value": pick["traded_value"],
    }

@app.get("/api/fno-ideas")
def get_fno_ideas(option_type: str = Query(default="CALL"), current_user: UserDB = Depends(get_current_user)):
    wanted_option_type = "PUT" if option_type.upper() == "PUT" else "CALL"
    wanted_direction = "FALL" if wanted_option_type == "PUT" else "RISE"
    picks, active_timeframe, computed_at = get_direction_scan(wanted_direction)

    ideas = [build_option_idea(pick, wanted_option_type) for pick in picks]

    sectors = {}
    for idea in ideas:
        sectors.setdefault(idea["sector"], [])
        if len(sectors[idea["sector"]]) < TOP_PICKS_PER_SECTOR:
            sectors[idea["sector"]].append(idea)

    # Sectors ordered by their most-liquid idea too, matching the ranking
    # rule for the ideas within them.
    sector_groups = [
        {"sector": sector, "picks": sector_picks}
        for sector, sector_picks in sorted(
            sectors.items(),
            key=lambda item: item[1][0]["traded_value"],
            reverse=True,
        )
    ]

    return {
        "option_type": wanted_option_type,
        "top_overall": ideas[:10],
        "sectors": sector_groups,
        "active_timeframe": active_timeframe,
        "total_available": len(ideas),
        "scanned_universe_size": len(DAILY_SCAN_UNIVERSE),
        "computed_at": computed_at.isoformat() if computed_at else None,
        "scan_cadence": "daily",
        "disclaimer": FNO_DISCLAIMER,
    }

# --- IPO TAB (open now / upcoming, sourced from a free third-party API) ---
IPO_GURU_BASE_URL = "https://api.ipoguru.in"
IPO_CACHE_SECONDS = 1800  # subscription/GMP figures don't move minute-to-minute
_ipo_cache = {}

def compute_ipo_confidence(gmp_percent, subscription_total):
    """Cheap, transparent heuristic - NOT sentiment. Higher grey-market
    premium and heavier subscription both read as stronger listing demand.
    Deliberately kept separate from the news-sentiment field below: both are
    derived from different inputs, and collapsing them into one label would
    make one number masquerade as two different claims."""
    gmp_percent = gmp_percent or 0
    subscription_total = subscription_total or 0
    score = clamp(gmp_percent * 1.5, -25, 25) + clamp((subscription_total - 1) * 4, -15, 25)
    # Same floor-at-50 confidence scale as build_algo_prediction/build_close_open_forecast.
    confidence_percent = round(clamp(50 + abs(score) * 1.2, 50, 92))
    outlook = "Strong Demand" if score >= 12 else "Weak Demand" if score <= -8 else "Moderate Demand"
    return confidence_percent, outlook

def fetch_ipo_news_sentiment(company_name):
    """Pre-listing companies have no ticker symbol, so this uses yfinance's
    free-text Search instead of Ticker.get_news, routed through the same
    news_pipeline the stock detail page uses - just keyed by company name
    (is_ticker=False) instead of a real NSE symbol. Isolated in its own
    try/except (mirrors evaluate_symbol_full's per-symbol isolation) so one
    company's lookup failing doesn't blank the whole IPO list. Stays strictly
    news-derived - falls back to the shared "no news found" shape rather than
    ever manufacturing a sentiment from the GMP/subscription numbers above."""
    try:
        raw_news = yf.Search(company_name, news_count=8, max_results=0, lists_count=0).news or []
    except Exception:
        return empty_news_sentiment()

    headlines = [title for article in raw_news if (title := extract_headline_title(article))]
    legacy = score_headlines(headlines)  # already returns empty_news_sentiment() when headlines is empty

    try:
        db = SessionLocal()
        try:
            rich = news_pipeline.get_or_refresh_stock_sentiment(
                db, company_name, company_name, None,
                lambda: news_normalize.normalize_yfinance_articles(raw_news, source="yfinance_search"),
                is_ticker=False, allow_llm_escalation=True,
            )
        finally:
            db.close()
    except Exception as exc:
        print(f"news_pipeline: rich IPO sentiment failed for {company_name}, falling back to legacy scan: {exc}")
        return legacy

    merged = dict(legacy)
    if rich["reason"] is None:
        merged["score"] = rich["legacy_score"]
        if legacy["label"] != "Mixed":
            merged["label"] = "Positive" if rich["legacy_score"] > 2 else "Negative" if rich["legacy_score"] < -2 else "Neutral"
        merged["note"] = (
            f"{rich['label']} news environment (score {rich['score']:+.0f}/100, confidence {rich['confidence']:.0%}) "
            f"across {rich['unique_event_count']} distinct event(s) from {rich['article_count']} article(s)."
        )
    merged.update({
        "confidence": rich["confidence"], "band_label": rich["label"], "raw_score": rich["score"],
        "article_count": rich["article_count"], "unique_event_count": rich["unique_event_count"],
        "positive_events": rich["positive_events"], "negative_events": rich["negative_events"],
        "neutral_events": rich["neutral_events"], "top_events": rich["top_events"],
        "windows": rich["windows"], "momentum": rich["momentum"], "reason": rich["reason"],
    })
    return merged

def get_cached_ipo_list(ipo_status):
    now = datetime.datetime.utcnow()
    cached = _ipo_cache.get(ipo_status)
    if cached and (now - cached["computed_at"]).total_seconds() < IPO_CACHE_SECONDS:
        return cached["data"]

    # NOTE: field names below (company_name, gmp_percent, subscription_total, ...)
    # are best-guess based on IPO Guru's published field list, not a verified
    # response sample - once a real API key is in and the endpoint returns actual
    # data, check one live response and adjust the .get() keys below to match.
    response = requests.get(
        f"{IPO_GURU_BASE_URL}/ipos",
        params={"status": ipo_status},
        headers={"X-API-KEY": IPO_GURU_API_KEY},
        timeout=10,
    )
    response.raise_for_status()
    raw_items = response.json().get("data", [])

    items = []
    for raw in raw_items:
        try:
            company_name = raw.get("company_name") or raw.get("name") or "Unknown"
            gmp_percent = raw.get("gmp_percent")
            subscription = raw.get("subscription") or {}
            subscription_total = raw.get("subscription_total", subscription.get("total"))
            confidence_percent, outlook = compute_ipo_confidence(gmp_percent, subscription_total)
            items.append({
                "company_name": company_name,
                "status": raw.get("status", ipo_status),
                "open_date": raw.get("open_date"),
                "close_date": raw.get("close_date"),
                "listing_date": raw.get("listing_date"),
                "price_band": raw.get("price_band"),
                "issue_price": raw.get("issue_price"),
                "lot_size": raw.get("lot_size"),
                "gmp_percent": gmp_percent,
                "subscription_total": subscription_total,
                "confidence_percent": confidence_percent,
                "outlook": outlook,
                "sentiment": fetch_ipo_news_sentiment(company_name),
            })
        except Exception as exc:
            print(f"Skipping one IPO entry due to error: {exc}")

    _ipo_cache[ipo_status] = {"data": items, "computed_at": now}
    return items

@app.get("/api/ipos")
def get_ipos(status: Literal["open", "upcoming"] = Query(...), current_user: UserDB = Depends(get_current_user)):
    if not IPO_GURU_API_KEY:
        return {"configured": False, "items": []}
    try:
        items = get_cached_ipo_list(status)
    except Exception as exc:
        print(f"IPO fetch failed: {exc}")
        return {"configured": True, "items": [], "error": "Could not reach the IPO data provider."}
    return {"configured": True, "items": items}

@app.post("/api/telegram/alert")
def send_telegram_alert(data: AlertData, current_user: UserDB = Depends(get_current_user)):
    trend_emoji = "🚀" if data.percent_change >= 0 else "📉"
    prediction_text = ""
    
    if data.prediction:
        active_algo = data.prediction.get("active", "INTRADAY").lower()
        active_prediction = data.prediction.get(active_algo, {})
        prediction_text = (
            f"\n\n*Active Algo:* {data.prediction.get('active', 'INTRADAY')}\n"
            f"*Prediction:* *{active_prediction.get('direction', 'N/A')}* "
            f"({active_prediction.get('rise_probability', 50)}% rise / "
            f"{active_prediction.get('fall_probability', 50)}% fall)\n"
            f"*Target:* Rs. {active_prediction.get('target_price', data.current_price)} | "
            f"*Confidence:* {active_prediction.get('confidence', 'Low')}"
        )

    message = (
        f"🚨 *PRO ALGO ALERT* 🚨\n\n"
        f"👤 *Trader:* {current_user.username}\n"
        f"📈 *Stock:* {data.symbol}\n"
        f"💵 *Price:* ₹{data.current_price} ({trend_emoji} {data.percent_change}%)\n"
        f"📊 *Volume:* {data.volume:,}\n\n"
        f"🎯 *Day High:* ₹{data.high} | 🔻 *Day Low:* ₹{data.low}\n\n"
        f"🤖 *Algo Signal:* *{data.suggestion}*"
        f"{prediction_text}"
    )
    
    send_telegram_message(message)
    return {"message": "Rich alert sent to Telegram!"}

# --- ALERTS (threshold-based price alerting) ---
@app.get("/api/alerts", response_model=list[AlertItemOut])
def get_alerts(current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(AlertRuleDB).filter(AlertRuleDB.user_id == current_user.id).all()

@app.post("/api/alerts", response_model=AlertItemOut)
def add_alert(item: AlertCreate, current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    new_item = AlertRuleDB(
        user_id=current_user.id, symbol=item.symbol.upper(),
        upper_threshold=item.upper_threshold, lower_threshold=item.lower_threshold,
        group_id=item.group_id,
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item

@app.delete("/api/alerts/{item_id}")
def delete_alert(item_id: int, current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(AlertRuleDB).filter(AlertRuleDB.id == item_id, AlertRuleDB.user_id == current_user.id).first()
    if item:
        db.delete(item)
        db.commit()
    return {"message": "Deleted"}

# --- PLAIN WATCHLIST (just tracking, no thresholds) ---
@app.get("/api/tracked-stocks", response_model=list[TrackedStockOut])
def get_tracked_stocks(current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(TrackedStockDB).filter(TrackedStockDB.user_id == current_user.id).all()

@app.post("/api/tracked-stocks", response_model=TrackedStockOut)
def add_tracked_stock(item: TrackedStockCreate, current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    new_item = TrackedStockDB(user_id=current_user.id, symbol=item.symbol.upper(), group_id=item.group_id)
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item

@app.delete("/api/tracked-stocks/{item_id}")
def delete_tracked_stock(item_id: int, current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(TrackedStockDB).filter(TrackedStockDB.id == item_id, TrackedStockDB.user_id == current_user.id).first()
    if item:
        db.delete(item)
        db.commit()
    return {"message": "Deleted"}

# --- CUSTOM GROUPS (named folders, shared by Watchlist + Alerts, up to 10 per type) ---
@app.get("/api/groups", response_model=list[StockGroupOut])
def get_groups(group_type: Literal["watchlist", "alert"] = Query(...), current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(StockGroupDB)
        .filter(StockGroupDB.user_id == current_user.id, StockGroupDB.group_type == group_type)
        .order_by(StockGroupDB.id)
        .all()
    )

@app.post("/api/groups", response_model=StockGroupOut)
def create_group(payload: StockGroupCreate, current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    existing_count = (
        db.query(StockGroupDB)
        .filter(StockGroupDB.user_id == current_user.id, StockGroupDB.group_type == payload.group_type)
        .count()
    )
    if existing_count >= MAX_GROUPS_PER_TYPE:
        raise HTTPException(status_code=400, detail=f"You can only have {MAX_GROUPS_PER_TYPE} groups per type.")
    new_group = StockGroupDB(user_id=current_user.id, group_type=payload.group_type, name=payload.name.strip())
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    return new_group

@app.put("/api/groups/{group_id}", response_model=StockGroupOut)
def rename_group(group_id: int, payload: StockGroupRename, current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    group = db.query(StockGroupDB).filter(StockGroupDB.id == group_id, StockGroupDB.user_id == current_user.id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")
    group.name = payload.name.strip()
    db.commit()
    db.refresh(group)
    return group

@app.delete("/api/groups/{group_id}")
def delete_group(group_id: int, current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    group = db.query(StockGroupDB).filter(StockGroupDB.id == group_id, StockGroupDB.user_id == current_user.id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")
    # Members are ungrouped, not deleted - losing a folder shouldn't silently
    # delete the stocks/alerts inside it.
    ungrouped_count = 0
    if group.group_type == "watchlist":
        ungrouped_count = db.query(TrackedStockDB).filter(TrackedStockDB.group_id == group_id).update({"group_id": None})
    else:
        ungrouped_count = db.query(AlertRuleDB).filter(AlertRuleDB.group_id == group_id).update({"group_id": None})
    db.delete(group)
    db.commit()
    return {"message": "Deleted", "ungrouped_count": ungrouped_count}