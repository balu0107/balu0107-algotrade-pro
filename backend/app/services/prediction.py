"""The hand-tuned prediction algorithm plus the news-sentiment glue that
feeds it a sentiment_score. Moved verbatim from main.py (Phase 2A, no
behavior change) except one bugfix noted inline below.
"""
import datetime

from news_pipeline import sentiment as news_sentiment
from news_pipeline import pipeline as news_pipeline
from news_pipeline import normalize as news_normalize

from .. import config
from ..database import SessionLocal
from . import market_data


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
        "confidence_percent": 50,  # bugfix (Phase 2A): the full-computation path always includes this key; the
        # early-exit shape omitted it, a latent None/KeyError risk for any caller assuming it's always present.
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
        "confidence": rich["confidence"], "band_label": rich["label"], "raw_score": rich["raw_score"],
        "article_count": rich["article_count"], "unique_event_count": rich["unique_event_count"],
        "unique_source_count": rich["unique_source_count"],
        "positive_events": rich["positive_events"], "negative_events": rich["negative_events"],
        "mixed_events": rich["mixed_events"], "neutral_events": rich["neutral_events"],
        "top_events": rich["top_events"],
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
        "rbi_repo_rate": config.RBI_REPO_RATE,
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
        intraday_history = market_data.get_history(stock.ticker, "5d", "5m")
        delivery_history = market_data.get_history(stock.ticker, "3mo", "1d")
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
    range_config = CANDLE_RANGES.get(range_key, CANDLE_RANGES["1M"])
    history = market_data.get_history(stock.ticker, range_config["period"], range_config["interval"])
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
