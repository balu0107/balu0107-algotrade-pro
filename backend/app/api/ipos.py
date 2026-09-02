import datetime
from typing import Literal

import requests
import yfinance as yf
from fastapi import APIRouter, Depends, Query

from news_pipeline import normalize as news_normalize
from news_pipeline import pipeline as news_pipeline

from .. import config
from ..database import SessionLocal
from ..models import UserDB
from ..security import get_current_user
from ..services.prediction import clamp, empty_news_sentiment, extract_headline_title, score_headlines

router = APIRouter()

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
        "confidence": rich["confidence"], "band_label": rich["label"], "raw_score": rich["raw_score"],
        "article_count": rich["article_count"], "unique_event_count": rich["unique_event_count"],
        "unique_source_count": rich["unique_source_count"],
        "positive_events": rich["positive_events"], "negative_events": rich["negative_events"],
        "mixed_events": rich["mixed_events"], "neutral_events": rich["neutral_events"],
        "top_events": rich["top_events"],
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
        headers={"X-API-KEY": config.IPO_GURU_API_KEY},
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


@router.get("/api/ipos")
def get_ipos(status: Literal["open", "upcoming"] = Query(...), current_user: UserDB = Depends(get_current_user)):
    if not config.IPO_GURU_API_KEY:
        return {"configured": False, "items": []}
    try:
        items = get_cached_ipo_list(status)
    except Exception as exc:
        print(f"IPO fetch failed: {exc}")
        return {"configured": True, "items": [], "error": "Could not reach the IPO data provider."}
    return {"configured": True, "items": items}
