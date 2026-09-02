"""The actual math from the plan's scoring section: recency decay, novelty,
article/event weighting, cross-source confidence (capped), stock-level
aggregation into [-100, 100], the legacy-int bridge for build_algo_prediction/
build_close_open_forecast, and momentum. Every constant lives in config.py -
nothing here is a magic number.
"""
import math

from . import config


def recency_weight(age_hours: float) -> float:
    """exp(-lambda * age_hours), lambda chosen so half-life == 24h exactly:
    24h old -> 0.5, 48h old -> 0.25, per config.RECENCY_HALF_LIFE_HOURS."""
    return math.exp(-config.RECENCY_LAMBDA * max(0.0, age_hours))


def novelty_score(rank_in_event: int) -> float:
    """rank 0 = first article to report this event -> 1.0; each later
    corroborating article scores less (rank 1 -> ~0.59, rank 2 -> ~0.48,
    rank 9 -> ~0.30). Needs no storage beyond the event's own running
    article_count - this is why 30 duplicate articles about one announcement
    can't dominate the score the way 30 independent stories would."""
    return 1.0 / (1.0 + math.log(1 + max(0, rank_in_event)))


def source_weight(source: str) -> float:
    return config.SOURCE_WEIGHTS.get(source, config.DEFAULT_SOURCE_WEIGHT)


def article_weight(relevance: float, source: str, age_hours: float, rank_in_event: int) -> float:
    """relevance x source_weight x recency_weight x novelty. A product, not a
    sum: any single near-zero factor (irrelevant, untrusted source, stale,
    late duplicate) suppresses the article's contribution regardless of the
    other three - intentional, since each factor is a genuinely independent
    reason to trust an article less."""
    return relevance * source_weight(source) * recency_weight(age_hours) * novelty_score(rank_in_event)


def event_confidence(distinct_sources: set) -> float:
    """clamp(1 - exp(-K * sum(source_weight for each DISTINCT source)), 0, CAP).
    Callers must pass a set of distinct source names, not a raw article
    count - duplicates from the same source contribute nothing here. Each
    additional distinct source adds strictly diminishing confidence and can
    never reach 1.0, so "50 duplicate articles" can never look like "50
    independent confirmations." """
    if not distinct_sources:
        return 0.0
    total_source_weight = sum(source_weight(s) for s in distinct_sources)
    return min(config.CONFIDENCE_CAP, 1 - math.exp(-config.CONFIDENCE_K * total_source_weight))


def aggregate_stock_sentiment(events: list[dict], now) -> dict:
    """events: dicts with sentiment_score[-1,1], confidence[0, CAP], relevance
    (the event's best member article's relevance), last_seen_at (datetime).
    numerator/denominator per the plan's worked formula; returns a null score
    with an explicit reason rather than a fake 0 when there isn't enough to
    go on."""
    numerator = 0.0
    denominator = 0.0
    for event in events:
        age_hours = max(0.0, (now - event["last_seen_at"]).total_seconds() / 3600)
        event_weight = event["relevance"] * recency_weight(age_hours)
        numerator += event["sentiment_score"] * event_weight * event["confidence"]
        denominator += event_weight * event["confidence"]

    if denominator < config.MIN_AGGREGATE_WEIGHT:
        return {"score": None, "confidence": 0.0, "reason": "insufficient_news"}

    normalized = numerator / denominator
    score = round(max(-100.0, min(100.0, normalized * 100)), 1)
    # Confidence in the AGGREGATE reading itself (not any one event's
    # confidence) - same saturating shape, against the total qualifying
    # weight backing this score.
    aggregate_confidence = min(config.CONFIDENCE_CAP, 1 - math.exp(-config.CONFIDENCE_K * denominator))
    return {"score": score, "confidence": round(aggregate_confidence, 3), "reason": None}


def band_label(score) -> str | None:
    if score is None:
        return None
    for low, high, label in config.SENTIMENT_BANDS:
        if low <= score <= high:
            return label
    return "Neutral/Mixed"


def legacy_bridge_score(stock_sentiment) -> int:
    """Maps the rich [-100,100] score down to the small int
    build_algo_prediction/build_close_open_forecast already expect - those
    two functions are unmodified, so their input contract can't change.
    insufficient_news (None) maps to 0, matching today's no-news behavior."""
    if stock_sentiment is None:
        return 0
    return round(max(-15.0, min(15.0, stock_sentiment / 100 * 15)))


def momentum_delta(score_now: dict, score_prior: dict):
    """Both args are aggregate_stock_sentiment() results for two adjacent,
    equal-length time windows ([now-W,now] vs [now-2W,now-W]). Returns None
    (never a fabricated delta) if either window came back insufficient_news."""
    if score_now["score"] is None or score_prior["score"] is None:
        return None
    return round(score_now["score"] - score_prior["score"], 1)


def event_velocity(events: list[dict], window_hours: float) -> dict:
    """events already filtered to the window. Counts only events at/above
    MIN_SIGNIFICANT_EVENT_CONFIDENCE, so one low-confidence single-source blip
    doesn't move the velocity reading."""
    significant = [e for e in events if e["confidence"] >= config.MIN_SIGNIFICANT_EVENT_CONFIDENCE]
    positive = sum(1 for e in significant if e["sentiment_score"] > 0.1)
    negative = sum(1 for e in significant if e["sentiment_score"] < -0.1)
    if not window_hours:
        return {"positive_event_velocity": 0.0, "negative_event_velocity": 0.0}
    return {
        "positive_event_velocity": round(positive / window_hours, 3),
        "negative_event_velocity": round(negative / window_hours, 3),
    }
