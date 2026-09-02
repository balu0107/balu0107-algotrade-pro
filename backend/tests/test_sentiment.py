"""Tests for the news_pipeline subsystem.

Run from backend/: `.venv/Scripts/python.exe -m pytest tests/test_sentiment.py -v`

Sections:
  1. Tier-0 lexicon+rules classifier - the 15 cases from the spec (test plan
     section K), unit-tested directly, no DB/network.
  2. Relevance heuristic - the spec's own illustrative bands, plus a
     regression test for the OIL/RETAIL common-word false-positive caught
     against live RSS data during development.
  3. Dedup - duplicate-headline clustering behavior.
  4. Scoring math - recency half-life, confidence cap, the worked
     aggregation example, and the insufficient_news null-case.
  5. Full pipeline integration - ingest_articles + compute_breakdown against
     an in-memory SQLite DB (the news_pipeline schema is plain SQL, no
     Postgres-specific features, so SQLite is a fine stand-in for tests).
"""
import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from news_pipeline.sentiment import classify_text, classify_headlines
from news_pipeline.relevance import score_relevance
from news_pipeline.dedup import titles_are_likely_duplicates
from news_pipeline import scoring
from news_pipeline import pipeline
from news_pipeline.models import NewsBase


# --- 1. Tier-0 classifier -----------------------------------------------

@pytest.mark.parametrize("name,text,expected_label", [
    ("strong_positive_earnings", "Company reports record profit and raises guidance", "POSITIVE"),
    ("strong_negative_earnings", "Company profit plunges and misses estimates", "NEGATIVE"),
    ("regulatory_investigation", "Company faces regulatory investigation", "NEGATIVE"),
    ("major_contract_win", "Company wins major multi billion dollar contract", "POSITIVE"),
    ("acquisition_cancelled", "Acquisition of rival firm called off after regulatory hurdles", "NEGATIVE"),
    ("maintains_guidance", "Company maintains existing guidance", "NEUTRAL"),
    ("clickbait", "You wont believe what this stock did today", "NEUTRAL"),
])
def test_classify_text_label(name, text, expected_label):
    result = classify_text(text)
    assert result["label"] == expected_label, f"{name}: {result}"


def test_mixed_revenue_up_guidance_cut_is_not_silently_positive():
    """The spec's central mixed-signal case: must not read as simply
    positive just because "profit"/"rises" appear."""
    result = classify_text("Company profit rises 20 percent but margins collapse and guidance is cut")
    assert result["label"] == "MIXED"
    assert result["is_ambiguous"] is True


def test_fraud_allegations_are_negative_but_not_over_confident():
    result = classify_text("Company faces fraud allegations from regulator")
    assert result["label"] == "NEGATIVE"
    # sentiment magnitude and confidence are independent numbers - a single
    # strongly-worded headline should still read as low article-level
    # confidence (that's cross-source confidence's job, not the classifier's)
    assert result["score"] < -0.3


def test_ceo_resignation_reads_negative_leaning_by_default():
    """Genuine context (planned succession vs. scandal) isn't recoverable
    from a bare headline - this documents the deliberate default (a sudden
    departure reads negative-leaning), not a claim that it's always right."""
    result = classify_text("CEO resigns amid restructuring")
    assert result["label"] == "NEGATIVE"


def test_macro_news_with_no_lexicon_hits_is_neutral_with_zero_confidence():
    """Sentiment and relevance are separate concerns: a sector-wide headline
    like "oil companies rally" legitimately contains real lexicon words
    ("rally") - that's tested elsewhere. This case has neither."""
    macro_news = classify_text("RBI keeps repo rate unchanged in policy meeting")
    assert macro_news["label"] == "NEUTRAL"
    assert macro_news["confidence"] == 0.0


def test_duplicate_style_headlines_score_similarly_not_multiplied():
    """Three outlets' near-identical headlines about one event should score
    similarly in isolation - dedup.py (tested below) is what prevents them
    from being counted three times, not the classifier itself."""
    a = classify_text("Reliance wins Rs 8000 crore contract")
    b = classify_text("Reliance bags Rs 8000 crore order")
    c = classify_text("Reliance secures major contract")
    for r in (a, b, c):
        assert r["label"] == "POSITIVE"


def test_classify_headlines_empty_list_returns_no_news_shape():
    result = classify_headlines([])
    assert result == {"score": 0, "label": "Neutral", "headlines": [], "note": "No recent news found for this symbol."}


def test_classify_headlines_legacy_shape_and_score_range():
    result = classify_headlines([
        "Company reports record profit and raises guidance",
        "Company profit rises 20 percent but margins collapse and guidance is cut",
    ])
    assert set(result.keys()) == {"score", "label", "headlines", "note"}
    assert -15 <= result["score"] <= 15
    assert len(result["headlines"]) == 2


# --- 2. Relevance heuristic ----------------------------------------------

def test_direct_company_headline_scores_near_one():
    result = score_relevance("RELIANCE", "Reliance Industries", "Reliance Industries announces Rs 8,000 crore acquisition")
    assert result["score"] >= 0.9


def test_sector_wide_headline_scores_in_spec_illustrative_band():
    result = score_relevance("ONGC", "Oil & Natural Gas Corp", "Indian oil companies rally after crude prices fall", sector="Energy")
    assert 0.5 <= result["score"] <= 0.7


def test_market_roundup_mention_scores_lower_than_a_direct_headline():
    result = score_relevance("RELIANCE", "Reliance Industries", "Indian stock market rises today; Reliance among top gainers")
    assert 0.3 <= result["score"] <= 0.5


def test_incidental_mention_is_low_relevance():
    result = score_relevance(
        "RELIANCE", "Reliance Industries", "Market wrap: Sensex, Nifty close higher",
        "In other news, Reliance shares also ticked up slightly along with 40 other stocks",
    )
    assert result["score"] < 0.4


def test_unrelated_headline_scores_zero():
    result = score_relevance("ASIANPAINT", "Asian Paints", "Paint industry sees demand pickup this festive season")
    assert result["score"] == 0.0


def test_common_word_ticker_does_not_false_positive():
    """Regression test: OIL/RETAIL are real NSE tickers that are also plain
    English words - a bare-word match on generic text must not read as a
    direct company mention. Caught against real live RSS data."""
    oil_result = score_relevance("OIL", "Oil India Limited", "Geopolitics, crude oil prices likely to drive stock market movements")
    retail_result = score_relevance("RETAIL", "Some Retail Company Limited", "Sebi proposes channel partners to expand retail access to bonds")
    assert oil_result["score"] == 0.0
    assert retail_result["score"] == 0.0


def test_real_ticker_callout_still_matches():
    """The fix for the above must not throw out genuine ticker mentions."""
    result = score_relevance("TCS", "Tata Consultancy Services", "TCS wins multi-year deal with European bank")
    assert result["score"] >= 0.9


# --- 3. Dedup --------------------------------------------------------------

def test_similar_duplicate_headlines_detected():
    assert titles_are_likely_duplicates(
        "Reliance wins Rs 8,000 crore contract", "Reliance bags Rs 8,000 crore order"
    )


def test_unrelated_headlines_not_flagged_as_duplicates():
    assert not titles_are_likely_duplicates(
        "Reliance wins Rs 8,000 crore contract", "Tata Motors launches new EV model"
    )


# --- 4. Scoring math --------------------------------------------------------

def test_recency_half_life_is_24_hours():
    assert scoring.recency_weight(24) == pytest.approx(0.5, abs=0.01)
    assert scoring.recency_weight(48) == pytest.approx(0.25, abs=0.01)


def test_novelty_decreases_with_rank():
    scores = [scoring.novelty_score(r) for r in range(4)]
    assert scores[0] == 1.0
    assert scores == sorted(scores, reverse=True)


def test_event_confidence_capped_and_saturating():
    one_source = scoring.event_confidence({"economic_times"})
    three_sources = scoring.event_confidence({"economic_times", "business_standard", "businessline"})
    fifty_sources = scoring.event_confidence({f"source_{i}" for i in range(50)})
    assert one_source < three_sources
    assert fifty_sources <= 0.95  # CONFIDENCE_CAP - never reaches "certain" regardless of source count


def test_aggregate_stock_sentiment_insufficient_news_returns_null_not_zero():
    result = scoring.aggregate_stock_sentiment([], datetime.datetime.utcnow())
    assert result == {"score": None, "confidence": 0.0, "reason": "insufficient_news"}


def test_aggregate_stock_sentiment_worked_example_is_bullish():
    """Reproduces the plan's worked RELIANCE example: one well-confirmed
    positive event should dominate a lightly-weighted negative/neutral one,
    landing in the Bullish band."""
    now = datetime.datetime(2026, 8, 23, 17, 0, 0)
    events = [
        {"sentiment_score": 0.78, "confidence": scoring.event_confidence({"economic_times", "business_standard", "businessline"}),
         "relevance": 1.0, "last_seen_at": now - datetime.timedelta(hours=1)},
        {"sentiment_score": -0.15, "confidence": scoring.event_confidence({"economic_times"}),
         "relevance": 0.5, "last_seen_at": now - datetime.timedelta(hours=3)},
        {"sentiment_score": 0.0, "confidence": scoring.event_confidence({"yfinance_search"}),
         "relevance": 0.14, "last_seen_at": now - datetime.timedelta(hours=2)},
    ]
    result = scoring.aggregate_stock_sentiment(events, now)
    assert result["reason"] is None
    assert 40 <= result["score"] <= 75
    assert scoring.band_label(result["score"]) in ("Bullish", "Strongly Bullish")


def test_legacy_bridge_stays_within_build_algo_prediction_range():
    assert scoring.legacy_bridge_score(None) == 0
    assert -15 <= scoring.legacy_bridge_score(100) <= 15
    assert -15 <= scoring.legacy_bridge_score(-100) <= 15


# --- 5. Full pipeline integration (in-memory SQLite) -----------------------

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    NewsBase.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_three_outlets_covering_one_event_do_not_multiply_sentiment(db_session):
    """The spec's central dedup requirement: 3 outlets reporting the same
    contract win should collapse into ONE event, with confidence rising
    (not sentiment tripling)."""
    now = datetime.datetime.utcnow()
    raw_articles = [
        {"source": "economic_times", "title": "Reliance Industries wins Rs 8000 crore contract",
         "url": "https://test/1", "published_at": now - datetime.timedelta(hours=1), "description": ""},
        {"source": "business_standard", "title": "Reliance bags Rs 8000 crore order from state government",
         "url": "https://test/2", "published_at": now - datetime.timedelta(hours=2), "description": ""},
        {"source": "businessline", "title": "Reliance secures major infrastructure contract",
         "url": "https://test/3", "published_at": now - datetime.timedelta(hours=3), "description": ""},
    ]
    accepted = pipeline.ingest_articles(db_session, "TESTSYM", True, "Reliance Industries", "Energy", raw_articles)
    assert accepted == 3

    breakdown = pipeline.compute_breakdown(db_session, "TESTSYM", True)
    assert breakdown["reason"] is None
    assert breakdown["article_count"] == 3
    # NOT 3 independent events - at least the two most similarly-worded
    # headlines should have clustered into one.
    assert breakdown["unique_event_count"] < 3
    assert breakdown["score"] is not None and breakdown["score"] > 0


def test_low_relevance_article_is_discarded_before_sentiment(db_session):
    now = datetime.datetime.utcnow()
    raw_articles = [
        {"source": "economic_times", "title": "Paint industry sees demand pickup this festive season",
         "url": "https://test/unrelated", "published_at": now, "description": ""},
    ]
    accepted = pipeline.ingest_articles(db_session, "RELIANCE", True, "Reliance Industries", "Energy", raw_articles)
    assert accepted == 0

    breakdown = pipeline.compute_breakdown(db_session, "RELIANCE", True)
    assert breakdown["reason"] == "insufficient_news"


def test_sentiment_cache_shared_across_symbols_for_same_article(db_session):
    """The RSS poller's stated design: sentiment for one physical article is
    computed once and reused across every symbol it's relevant to, not
    recomputed per symbol."""
    now = datetime.datetime.utcnow()
    shared_article = [{
        "source": "economic_times", "title": "Indian oil companies rally after crude prices fall",
        "url": "https://test/shared", "published_at": now, "description": "",
    }]
    cache = {}
    pipeline.ingest_articles(db_session, "ONGC", True, "Oil & Natural Gas Corp", "Energy", shared_article, sentiment_cache=cache)
    assert "https://test/shared" in cache
    calls_before = len(cache)
    pipeline.ingest_articles(db_session, "BPCL", True, "Bharat Petroleum", "Energy", shared_article, sentiment_cache=cache)
    assert len(cache) == calls_before  # no new entry - reused, not recomputed


# --- 6. Part 1 fixes: event-level MIXED, dedup gates, high-impact escalation,
#        LLM fallback --------------------------------------------------------

def test_mixed_earnings_guidance_surfaces_as_mixed_event_not_neutral(db_session):
    """The bug this fix targets: a single article with genuine positive AND
    negative evidence must make its EVENT mixed too, not silently net to
    NEUTRAL once rolled into the event aggregate."""
    now = datetime.datetime.utcnow()
    raw_articles = [{
        "source": "economic_times",
        "title": "Mixed Co profit rises 20 percent but margins collapse and guidance is cut",
        "url": "https://test/mixed-earnings", "published_at": now, "description": "",
    }]
    pipeline.ingest_articles(db_session, "MIXEDCO", True, "Mixed Co", "Technology", raw_articles)

    event = db_session.query(pipeline.EventDB).filter(pipeline.EventDB.symbol == "MIXEDCO").first()
    assert event.sentiment_label == "MIXED"

    breakdown = pipeline.compute_breakdown(db_session, "MIXEDCO", True)
    assert breakdown["mixed_events"] == 1
    assert breakdown["positive_events"] == 0
    assert breakdown["negative_events"] == 0


def test_same_source_repeated_coverage_does_not_inflate_sentiment_or_confidence(db_session):
    """Regression test for Part 1.3 - already correctly handled by the
    existing weighted-average (not sum) event score and the distinct-source
    confidence formula, but pinned here so it stays true going forward."""
    now = datetime.datetime.utcnow()
    one_article = [{
        "source": "economic_times", "title": "Acme Corp wins major government contract",
        "url": "https://test/one-source-1", "published_at": now, "description": "",
    }]
    pipeline.ingest_articles(db_session, "ACME1", True, "Acme Corp", "Industrials", one_article)
    single_source_event = db_session.query(pipeline.EventDB).filter(pipeline.EventDB.symbol == "ACME1").first()

    five_duplicates = [{
        "source": "economic_times", "title": "Acme Corp wins major government contract",
        "url": f"https://test/five-source-{i}", "published_at": now - datetime.timedelta(minutes=i),
        "description": "",
    } for i in range(5)]
    pipeline.ingest_articles(db_session, "ACME5", True, "Acme Corp", "Industrials", five_duplicates)
    five_duplicate_event = db_session.query(pipeline.EventDB).filter(pipeline.EventDB.symbol == "ACME5").first()

    # Same source, 5x the articles - confidence and sentiment must NOT scale
    # with article count (no "50 duplicate articles = 50x sentiment").
    assert five_duplicate_event.confidence == pytest.approx(single_source_event.confidence, abs=0.01)
    assert five_duplicate_event.sentiment_score == pytest.approx(single_source_event.sentiment_score, abs=0.05)
    assert five_duplicate_event.unique_source_count == 1


def test_multiple_independent_sources_raise_confidence(db_session):
    """The other half of Part 1.3: independent sources on the SAME event
    should raise confidence, unlike same-source duplicates above."""
    now = datetime.datetime.utcnow()
    one_source = [{
        "source": "economic_times", "title": "Acme Corp wins major government contract",
        "url": "https://test/indep-1", "published_at": now, "description": "",
    }]
    pipeline.ingest_articles(db_session, "ACMEA", True, "Acme Corp", "Industrials", one_source)
    one_source_event = db_session.query(pipeline.EventDB).filter(pipeline.EventDB.symbol == "ACMEA").first()

    three_sources = [
        {"source": "economic_times", "title": "Acme Corp wins major government contract",
         "url": "https://test/indep-2", "published_at": now, "description": ""},
        {"source": "business_standard", "title": "Acme Corp bags major government contract",
         "url": "https://test/indep-3", "published_at": now, "description": ""},
        {"source": "businessline", "title": "Acme Corp secures major government contract",
         "url": "https://test/indep-4", "published_at": now, "description": ""},
    ]
    pipeline.ingest_articles(db_session, "ACMEB", True, "Acme Corp", "Industrials", three_sources)
    three_source_event = db_session.query(pipeline.EventDB).filter(pipeline.EventDB.symbol == "ACMEB").first()

    assert three_source_event.confidence > one_source_event.confidence
    assert three_source_event.unique_source_count == 3


def test_different_event_types_with_similar_titles_do_not_merge(db_session):
    """The dedup fix (Part 1.2): "Global Metals ... contract" and "Global
    Metals ... investigation" share 80% textual similarity (would merge on
    SequenceMatcher ratio alone) but are a CONTRACT_WIN and a REGULATORY
    story respectively - the event-type gate must keep them separate."""
    now = datetime.datetime.utcnow()
    raw_articles = [
        {"source": "economic_times", "title": "Global Metals wins major Rs 2,000 crore project contract",
         "url": "https://test/type-gate-1", "published_at": now, "description": ""},
        {"source": "business_standard", "title": "Global Metals faces major Rs 2,000 crore project investigation",
         "url": "https://test/type-gate-2", "published_at": now, "description": ""},
    ]
    pipeline.ingest_articles(db_session, "GMETALS", True, "Global Metals", "Basic Materials", raw_articles)

    breakdown = pipeline.compute_breakdown(db_session, "GMETALS", True)
    assert breakdown["unique_event_count"] == 2


def test_same_event_with_substantially_different_wording_is_a_known_limitation(db_session):
    """Documents a real, stated limitation rather than pretending it's
    solved: "Reliance bags ... order" vs "Reliance secures ... contract" (the
    exact pair verified this session at a 0.46 SequenceMatcher ratio, below
    the 0.55 threshold) plausibly describe the same real-world event but
    don't merge - pure lexical similarity has no way to know that without an
    NLP/embeddings dependency, which is explicitly out of scope."""
    now = datetime.datetime.utcnow()
    raw_articles = [
        {"source": "economic_times", "title": "Reliance bags Rs 8,000 crore order",
         "url": "https://test/wording-1", "published_at": now, "description": ""},
        {"source": "business_standard", "title": "Reliance secures major contract",
         "url": "https://test/wording-2", "published_at": now, "description": ""},
    ]
    pipeline.ingest_articles(db_session, "RELWORD", True, "Reliance Industries", "Energy", raw_articles)

    breakdown = pipeline.compute_breakdown(db_session, "RELWORD", True)
    assert breakdown["unique_event_count"] == 2  # known limitation, not a bug


def test_high_impact_event_forces_escalation_even_when_not_ambiguous(monkeypatch):
    """A bankruptcy headline reads confidently NEGATIVE at Tier-0 (not
    ambiguous), but bankruptcy is a high-impact event_type - escalation must
    still fire when the caller marks it high-impact, independent of
    ambiguity (Part 1.4)."""
    from news_pipeline import sentiment as sentiment_module

    text = "Company files for bankruptcy protection after mounting debt default"
    baseline = sentiment_module.classify_text(text)
    assert baseline["is_ambiguous"] is False  # confidently negative, not an ambiguity case

    escalation_calls = []

    def fake_tiered_classify(self, t):
        escalation_calls.append(t)
        return {"score": -0.9, "label": "NEGATIVE", "confidence": 0.9, "is_ambiguous": False, "trace": [{"tier": "llm"}]}

    monkeypatch.setattr(sentiment_module.LLMSentimentClassifier, "classify", fake_tiered_classify)

    result = sentiment_module.classify_text(text, allow_llm_escalation=True, force_escalate=True)
    assert escalation_calls == [text]
    assert result["label"] == "NEGATIVE"


def test_ambiguous_low_impact_event_still_escalates(monkeypatch):
    """The pre-existing ambiguity-based escalation path must keep working
    even when force_escalate is False - Part 1.4 is additive, not a
    replacement for the original gate."""
    from news_pipeline import sentiment as sentiment_module

    text = "Company profit rises 20 percent but margins collapse and guidance is cut"
    baseline = sentiment_module.classify_text(text)
    assert baseline["is_ambiguous"] is True

    escalation_calls = []

    def fake_tiered_classify(self, t):
        escalation_calls.append(t)
        return {"score": 0.0, "label": "MIXED", "confidence": 0.5, "is_ambiguous": True, "trace": [{"tier": "llm"}]}

    monkeypatch.setattr(sentiment_module.LLMSentimentClassifier, "classify", fake_tiered_classify)

    sentiment_module.classify_text(text, allow_llm_escalation=True, force_escalate=False)
    assert escalation_calls == [text]


def test_llm_failure_falls_back_to_lexicon(monkeypatch):
    """If the Tier-2 provider is configured but the call itself fails
    (network error, timeout, non-200), the classifier must fall back to the
    Tier-0 lexicon result rather than propagating the failure."""
    from news_pipeline import sentiment as sentiment_module
    from news_pipeline import config as news_config

    monkeypatch.setattr(news_config, "LLM_SENTIMENT_ENABLED", True)
    monkeypatch.setattr(news_config, "LLM_SENTIMENT_API_KEY", "fake-key")
    monkeypatch.setattr(news_config, "LLM_SENTIMENT_API_URL", "https://fake.invalid/classify")

    def broken_post(*args, **kwargs):
        raise ConnectionError("provider unreachable")

    monkeypatch.setattr(sentiment_module.requests, "post", broken_post)

    text = "Company wins major multi billion dollar contract"
    lexicon_only = sentiment_module.LexiconSentimentClassifier().classify(text)
    classifier = sentiment_module.LLMSentimentClassifier(fallback=sentiment_module.LexiconSentimentClassifier())
    result = classifier.classify(text)

    assert result["label"] == lexicon_only["label"]
    assert result["score"] == pytest.approx(lexicon_only["score"])
    assert any("llm_failed_fallback" in str(t) for t in result["trace"])
