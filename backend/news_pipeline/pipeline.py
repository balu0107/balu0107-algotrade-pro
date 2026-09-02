"""Orchestrates the on-demand path: normalize -> relevance -> dedup into
events -> Tier-0 (or gated Tier-2) sentiment -> persist -> aggregate.

The once-daily ~2,300-symbol scan deliberately bypasses ALL of this - it keeps
calling main.py's analyze_news_sentiment/get_cached_news_sentiment/
score_headlines exactly as before this package existed (same yfinance call
count, zero DB writes). This module is reached only from low-volume,
high-value call sites: a single stock's detail page, the news-sentiment
endpoint, and the RSS poller - per the plan's cost-control ordering.
"""
import datetime

from . import config, scoring, dedup
from .relevance import score_relevance
from .sentiment import classify_text
from .event_types import classify_event_type
from .models import ArticleDB, EventDB, ArticleEventMapDB, SentimentScoreCacheDB

# Tracks the last time we actually fetched+ingested new raw articles for a
# symbol, in-memory - same TTL-dict idiom main.py already uses everywhere
# (_news_sentiment_cache, _ipo_cache, ...), so a burst of requests for the
# same symbol doesn't re-fetch/re-ingest on every single one.
_last_ingest_at = {}


def _recompute_event_from_members(db, event):
    """Recomputes one event's aggregate sentiment/confidence/relevance/
    summary from its current member articles - simpler and less bug-prone
    than maintaining a running incremental average, and cheap since events
    rarely have more than a handful of members.

    Event label (Part 1.1): derived from weighted POSITIVE vs. NEGATIVE
    evidence across members, not just the net average score - a member
    article the Tier-0 classifier already called MIXED is known to carry
    genuine evidence on BOTH sides (config.MIXED_ARTICLE_EVIDENCE_FLOOR), and
    two separately one-sided members each count as evidence on their own
    side. The event is MIXED when both sides clear
    config.EVENT_MIXED_MIN_EVIDENCE_FRACTION of the total weighted evidence -
    this is what lets a single genuinely-mixed article (or two opposed
    articles) surface as MIXED instead of silently netting to NEUTRAL."""
    members = (
        db.query(ArticleDB)
        .join(ArticleEventMapDB, ArticleEventMapDB.article_id == ArticleDB.id)
        .filter(ArticleEventMapDB.event_id == event.id)
        .order_by(ArticleDB.published_at.asc())
        .all()
    )
    if not members:
        return

    now = datetime.datetime.utcnow()
    numerator = 0.0
    denominator = 0.0
    positive_evidence = 0.0
    negative_evidence = 0.0
    distinct_sources = set()
    best_relevance = 0.0
    best_weight_for_summary = -1.0
    summary_title = event.event_summary

    for rank, article in enumerate(members):
        distinct_sources.add(article.source)
        best_relevance = max(best_relevance, article.relevance_score or 0.0)
        age_hours = (now - article.published_at).total_seconds() / 3600
        weight = scoring.article_weight(article.relevance_score or 0.0, article.source, age_hours, rank)
        score = article.sentiment_score or 0.0
        numerator += score * weight
        denominator += weight

        if article.sentiment_label == "MIXED":
            positive_evidence += weight * config.MIXED_ARTICLE_EVIDENCE_FLOOR
            negative_evidence += weight * config.MIXED_ARTICLE_EVIDENCE_FLOOR
        elif score > 0:
            positive_evidence += weight * score
        elif score < 0:
            negative_evidence += weight * (-score)

        source_trust = scoring.source_weight(article.source)
        if source_trust > best_weight_for_summary:
            best_weight_for_summary = source_trust
            summary_title = article.title

    event.sentiment_score = round(numerator / denominator, 3) if denominator > 0 else 0.0
    total_evidence = positive_evidence + negative_evidence
    is_mixed = (
        total_evidence > 0
        and positive_evidence >= config.EVENT_MIXED_MIN_EVIDENCE_FRACTION * total_evidence
        and negative_evidence >= config.EVENT_MIXED_MIN_EVIDENCE_FRACTION * total_evidence
    )
    if is_mixed:
        event.sentiment_label = "MIXED"
    elif event.sentiment_score > 0.1:
        event.sentiment_label = "POSITIVE"
    elif event.sentiment_score < -0.1:
        event.sentiment_label = "NEGATIVE"
    else:
        event.sentiment_label = "NEUTRAL"
    event.confidence = scoring.event_confidence(distinct_sources)
    event.relevance = best_relevance
    event.unique_source_count = len(distinct_sources)
    event.article_count = len(members)
    event.event_summary = summary_title
    event.last_seen_at = max(a.published_at for a in members)
    event.event_timestamp = min(a.published_at for a in members)


def _entity_column(is_ticker: bool):
    """Both ArticleDB and EventDB carry two entity columns - `symbol` for a
    real NSE ticker, `company_query` for a no-ticker lookup (e.g. a
    pre-listing IPO company). Every query/write below goes through this one
    switch so a ticker's rows and a company-name's rows never collide, and a
    future company_query-keyed feature (IPO sentiment) already has a real,
    exercised code path instead of a stub."""
    return "symbol" if is_ticker else "company_query"


def ingest_articles(db, entity_key, is_ticker, company_name, sector, raw_articles, allow_llm_escalation=False, sentiment_cache=None) -> int:
    """raw_articles: already-normalized dicts {source, title, url,
    published_at, description}. Persists every article (discarded ones too,
    with a reason - an audit trail, not a silent drop), scores/dedupes/
    clusters the ones that clear the relevance bar, and commits. Returns how
    many articles cleared relevance.

    sentiment_cache is an optional dict the CALLER owns and reuses across
    multiple ingest_articles() calls for the same raw article text (the RSS
    poller does this across every symbol one market-wide story matches) -
    sentiment is a property of the TEXT, not of which symbol it's being
    filed under, so it should only ever be computed once per unique article,
    not once per (article, symbol) pair."""
    now = datetime.datetime.utcnow()
    accepted_count = 0
    column = _entity_column(is_ticker)

    cutoff = now - datetime.timedelta(hours=dedup.DEDUP_TIME_WINDOW_HOURS)
    existing_events = db.query(EventDB).filter(getattr(EventDB, column) == entity_key, EventDB.last_seen_at >= cutoff).all()
    event_candidates = [
        {"id": e.id, "event_summary": e.event_summary, "event_type": e.event_type, "last_seen_at": e.last_seen_at}
        for e in existing_events
    ]
    events_by_id = {e.id: e for e in existing_events}
    touched_event_ids = set()

    for raw in raw_articles:
        # A single article can legitimately be relevant to several symbols
        # (a sector-wide story), so dedup is scoped to (url, this entity),
        # not the url alone - re-ingesting the SAME (url, entity) pair twice
        # is what this guards against.
        already_have = (
            db.query(ArticleDB)
            .filter(ArticleDB.source_url == raw["url"], getattr(ArticleDB, column) == entity_key)
            .first()
        )
        if already_have:
            continue

        relevance_result = score_relevance(entity_key, company_name, raw["title"], raw.get("description", ""), sector)
        relevance = relevance_result["score"]

        article = ArticleDB(
            source=raw["source"], source_url=raw["url"], title=raw["title"],
            description=raw.get("description"), published_at=raw["published_at"], fetched_at=now,
            symbol=entity_key if is_ticker else None, company_query=None if is_ticker else entity_key,
            title_hash=dedup.normalize_title(raw["title"]), relevance_score=relevance, created_at=now,
        )

        if relevance < config.RELEVANCE_DISCARD_THRESHOLD:
            article.discarded_reason = "low_relevance"
            db.add(article)
            continue

        # event_type is computed BEFORE sentiment so a high-impact category
        # (earnings, fraud, bankruptcy, ...) can force LLM escalation even
        # when Tier-0 itself doesn't flag the text as ambiguous - see
        # config.HIGH_IMPACT_EVENT_TYPES. Still fully gated behind the
        # caller's own allow_llm_escalation (the daily scan/RSS poller pass
        # False, so this never escalates from those paths regardless).
        event_type = classify_event_type(f"{raw['title']} {raw.get('description') or ''}")
        is_high_impact = event_type in config.HIGH_IMPACT_EVENT_TYPES

        cache_key = raw["url"]
        if sentiment_cache is not None and cache_key in sentiment_cache:
            sentiment_result = sentiment_cache[cache_key]
        else:
            sentiment_result = classify_text(
                f"{raw['title']}. {raw.get('description') or ''}",
                allow_llm_escalation=allow_llm_escalation, force_escalate=is_high_impact,
            )
            if sentiment_cache is not None:
                sentiment_cache[cache_key] = sentiment_result
        article.sentiment_score = sentiment_result["score"]
        article.sentiment_label = sentiment_result["label"]
        article.sentiment_tier = "llm" if any(t.get("tier") == "llm" for t in sentiment_result.get("trace", []) if isinstance(t, dict)) else "lexicon"
        db.add(article)
        db.flush()  # need article.id for the event mapping row below

        matched = dedup.find_matching_event(raw["title"], raw["published_at"], event_type, event_candidates)
        if matched:
            event = events_by_id[matched["id"]]
        else:
            event = EventDB(
                symbol=entity_key if is_ticker else None, company_query=None if is_ticker else entity_key,
                event_cluster_key=dedup.normalize_title(raw["title"]),
                event_type=event_type,
                event_summary=raw["title"], event_timestamp=raw["published_at"], last_seen_at=raw["published_at"],
                sentiment_score=0.0, confidence=0.0, relevance=0.0, article_count=0, unique_source_count=0,
            )
            db.add(event)
            db.flush()
            events_by_id[event.id] = event
            event_candidates.append({
                "id": event.id, "event_summary": event.event_summary,
                "event_type": event.event_type, "last_seen_at": event.last_seen_at,
            })

        db.add(ArticleEventMapDB(article_id=article.id, event_id=event.id))
        db.flush()
        touched_event_ids.add(event.id)
        accepted_count += 1

    for event_id in touched_event_ids:
        _recompute_event_from_members(db, events_by_id[event_id])

    db.commit()
    return accepted_count


def _events_dicts_in_window(db, entity_key, is_ticker, window_start, window_end):
    column = _entity_column(is_ticker)
    events = (
        db.query(EventDB)
        .filter(getattr(EventDB, column) == entity_key, EventDB.last_seen_at >= window_start, EventDB.last_seen_at < window_end)
        .all()
    )
    return [
        {
            "id": e.id, "sentiment_score": e.sentiment_score, "sentiment_label": e.sentiment_label,
            "confidence": e.confidence, "relevance": e.relevance, "last_seen_at": e.last_seen_at,
            "event_summary": e.event_summary, "event_type": e.event_type,
            "unique_source_count": e.unique_source_count, "article_count": e.article_count,
        }
        for e in events
    ]


def _distinct_source_count(db, event_ids) -> int:
    """Aggregate distinct sources across MULTIPLE events - each EventDB row
    only stores its own member count, not which sources, so this queries the
    underlying articles directly via the mapping table."""
    if not event_ids:
        return 0
    sources = (
        db.query(ArticleDB.source)
        .join(ArticleEventMapDB, ArticleEventMapDB.article_id == ArticleDB.id)
        .filter(ArticleEventMapDB.event_id.in_(event_ids))
        .distinct()
        .all()
    )
    return len(sources)


def compute_breakdown(db, entity_key, is_ticker) -> dict:
    """Builds the full rich response shape from news_events - cheap enough
    (a handful of small queries + arithmetic) to run on every call; the
    SentimentScoreCacheDB table exists to skip this on a tight TTL and to let
    the last computed numbers be inspected in psql after a restart, not
    because this step itself is expensive."""
    now = datetime.datetime.utcnow()
    windows = {}
    for name, hours in config.WINDOW_HOURS.items():
        window_events = _events_dicts_in_window(db, entity_key, is_ticker, now - datetime.timedelta(hours=hours), now)
        windows[name] = scoring.aggregate_stock_sentiment(window_events, now)

    momentum = {}
    for name in config.MOMENTUM_WINDOWS:
        hours = config.WINDOW_HOURS[name]
        now_events = _events_dicts_in_window(db, entity_key, is_ticker, now - datetime.timedelta(hours=hours), now)
        prior_events = _events_dicts_in_window(db, entity_key, is_ticker, now - datetime.timedelta(hours=2 * hours), now - datetime.timedelta(hours=hours))
        score_now = scoring.aggregate_stock_sentiment(now_events, now)
        score_prior = scoring.aggregate_stock_sentiment(prior_events, now - datetime.timedelta(hours=hours))
        momentum[f"sentiment_change_{name}"] = scoring.momentum_delta(score_now, score_prior)

    day_events = _events_dicts_in_window(db, entity_key, is_ticker, now - datetime.timedelta(hours=24), now)
    momentum.update(scoring.event_velocity(day_events, 24))

    # Event label (spec: POSITIVE | NEGATIVE | NEUTRAL | MIXED) drives these
    # four buckets directly now that _recompute_event_from_members can
    # actually assign MIXED - previously this was inferred purely from the
    # numeric score, which is exactly how a genuinely mixed event's evidence
    # got silently counted as "neutral" instead of being visible as MIXED.
    positive_events = sum(1 for e in day_events if e["sentiment_label"] == "POSITIVE")
    negative_events = sum(1 for e in day_events if e["sentiment_label"] == "NEGATIVE")
    mixed_events = sum(1 for e in day_events if e["sentiment_label"] == "MIXED")
    neutral_events = len(day_events) - positive_events - negative_events - mixed_events
    top_events = sorted(day_events, key=lambda e: e["relevance"] * e["confidence"], reverse=True)[:5]

    primary = windows["24h"]
    return {
        "symbol": entity_key,
        "score": primary["score"],  # normalized display score, [-100, 100]
        "raw_score": round(primary["score"] / 100, 3) if primary["score"] is not None else None,  # raw sentiment, [-1, 1]
        "label": scoring.band_label(primary["score"]),
        # "confidence" here is a heuristic evidence-strength measure (how much
        # qualifying weighted evidence backs the score), NOT a calibrated
        # probability - it has never been checked against actual outcomes.
        "confidence": primary["confidence"],
        "reason": primary["reason"],
        "article_count": sum(e["article_count"] for e in day_events),
        "unique_event_count": len(day_events),
        "unique_source_count": _distinct_source_count(db, [e["id"] for e in day_events]),
        "positive_events": positive_events,
        "negative_events": negative_events,
        "mixed_events": mixed_events,
        "neutral_events": neutral_events,
        "top_events": [
            {
                "event": e["event_summary"], "event_type": e["event_type"],
                "sentiment": e["sentiment_score"], "sentiment_label": e["sentiment_label"],
                "confidence": e["confidence"], "source_count": e["unique_source_count"],
            }
            for e in top_events
        ],
        "windows": windows,
        "momentum": momentum,
        "legacy_score": scoring.legacy_bridge_score(primary["score"]),
        "computed_at": now.isoformat(),
    }


def _upsert_cache(db, entity_key, breakdown):
    # SentimentScoreCacheDB.symbol doubles as a generic entity key (ticker or
    # company-name slug) - it's a cache table's primary key string, not a
    # claim that this row always represents a real tradeable ticker.
    row = db.query(SentimentScoreCacheDB).filter(SentimentScoreCacheDB.symbol == entity_key).first()
    if row is None:
        row = SentimentScoreCacheDB(symbol=entity_key)
        db.add(row)
    row.score_1h, row.confidence_1h = breakdown["windows"]["1h"]["score"], breakdown["windows"]["1h"]["confidence"]
    row.score_6h, row.confidence_6h = breakdown["windows"]["6h"]["score"], breakdown["windows"]["6h"]["confidence"]
    row.score_24h, row.confidence_24h = breakdown["windows"]["24h"]["score"], breakdown["windows"]["24h"]["confidence"]
    row.score_7d, row.confidence_7d = breakdown["windows"]["7d"]["score"], breakdown["windows"]["7d"]["confidence"]
    row.article_count_24h = breakdown["article_count"]
    row.event_count_24h = breakdown["unique_event_count"]
    row.computed_at = datetime.datetime.utcnow()
    db.commit()


def get_or_refresh_stock_sentiment(db, entity_key, company_name, sector, fetch_raw_articles, is_ticker=True, allow_llm_escalation=False) -> dict:
    """The on-demand entry point. entity_key is a real NSE ticker when
    is_ticker=True (the stock detail page, /api/news-sentiment/{symbol}), or
    a free-text company name for a no-ticker lookup (IPO cards) when False.
    fetch_raw_articles is a zero-arg callable supplied by the caller that
    hits yfinance/RSS and returns already-normalized article dicts - kept out
    of this module so news_pipeline never needs to import yfinance/main.py
    directly. Only re-fetches/re-ingests when this entity's last ingest is
    older than NEWS_SENTIMENT_DB_CACHE_SECONDS."""
    now = datetime.datetime.utcnow()
    cache_key = (entity_key, is_ticker)
    last_ingest = _last_ingest_at.get(cache_key)
    if not last_ingest or (now - last_ingest).total_seconds() >= config.NEWS_SENTIMENT_DB_CACHE_SECONDS:
        try:
            raw_articles = fetch_raw_articles()
            if raw_articles:
                ingest_articles(db, entity_key, is_ticker, company_name, sector, raw_articles, allow_llm_escalation)
        except Exception as exc:
            print(f"news_pipeline: on-demand ingest failed for {entity_key}: {exc}")
        _last_ingest_at[cache_key] = now

    breakdown = compute_breakdown(db, entity_key, is_ticker)
    _upsert_cache(db, entity_key, breakdown)
    return breakdown
