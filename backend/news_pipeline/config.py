"""Every tunable weight, decay constant, and threshold for the news-sentiment
pipeline lives here, in one place - nothing here is asserted as scientifically
correct. These are documented starting points meant to be recalibrated later
against real historical outcomes, not hardcoded scattered through the pipeline
modules. See ARCHITECTURE.md-style notes inline for why each constant exists.
"""

# --- Source trust weights (spec section 5) -----------------------------------
# Reuters is deliberately absent: their free public RSS was discontinued years
# ago (confirmed unreachable), so it isn't a real source in this app. Illustrative
# only - recalibrate once enough history exists to check which sources actually
# lead vs. lag price moves.
SOURCE_WEIGHTS = {
    "economic_times": 0.90,
    "business_standard": 0.90,
    "businessline": 0.85,
    "yfinance_ticker": 0.75,   # Yahoo's own aggregated feed, not one named outlet
    "yfinance_search": 0.70,   # free-text search results - weakest entity precision
}
DEFAULT_SOURCE_WEIGHT = 0.6  # unrecognized source -> conservative floor, never 0

# --- Relevance heuristic (spec section 2) ------------------------------------
RELEVANCE_TITLE_MATCH = 1.0            # ticker/canonical name found in the title
RELEVANCE_ALIAS_TITLE_MATCH = 0.85     # a known alias/short-name found in the title
RELEVANCE_NAME_IN_DESCRIPTION = 0.55   # name/alias only in the description, not title
RELEVANCE_SECTOR_KEYWORD_BASE = 0.5    # sector-wide article, symbol's sector matched
RELEVANCE_SECTOR_KEYWORD_STEP = 0.1    # + per extra distinct sector keyword hit
RELEVANCE_SECTOR_KEYWORD_CAP = 0.7
RELEVANCE_TITLE_POSITION_BONUS = 0.1   # mention lands in the first N chars of the title
RELEVANCE_TITLE_POSITION_CHARS = 40
ROUNDUP_DISCOUNT = 0.5                 # multiplier when a market-roundup phrase co-occurs
ROUNDUP_SHARED_MENTION_DISCOUNT = 0.85 # extra multiplier per additional distinct company named alongside
RELEVANCE_DISCARD_THRESHOLD = 0.15     # below this, the article is dropped BEFORE sentiment ever runs

# --- Recency decay (spec section 6) ------------------------------------------
# half-life = 24h reproduces the spec's own worked example exactly:
# 24h old -> 0.5, 48h old -> 0.25. Chosen because Indian-equity news impact
# fades within roughly one to two trading sessions, while still leaving a
# non-trivial tail out to 7 days (no hard cutoff).
import math
RECENCY_HALF_LIFE_HOURS = 24.0
RECENCY_LAMBDA = math.log(2) / RECENCY_HALF_LIFE_HOURS

# --- Novelty (spec section 7) ------------------------------------------------
# novelty(rank) = 1 / (1 + ln(1 + rank)); rank 0 (first article in an event) -> 1.0,
# rank 1 -> ~0.59, rank 2 -> ~0.48, rank 9 -> ~0.30. Smooth diminishing returns,
# no storage needed beyond the event's own running article_count.

# --- Cross-source confidence (spec section 9) --------------------------------
# event_confidence = clamp(1 - exp(-K * sum_of_distinct_source_weights), 0, CAP).
# Duplicates from the SAME source contribute nothing (deduped before summing);
# each additional DISTINCT source adds strictly diminishing confidence and can
# never reach 1.0, so "50 duplicate articles" can never look like "50 independent
# confirmations."
CONFIDENCE_K = 0.5
CONFIDENCE_CAP = 0.95

# --- Event-level MIXED detection (Part 1.1) ----------------------------------
# An event's label is derived from weighted POSITIVE vs. NEGATIVE evidence
# across its member articles, not just the net average score - a single
# article already labeled MIXED (real positive AND negative content) or two
# separately one-sided articles both count as evidence on their respective
# side. MIXED_ARTICLE_EVIDENCE_FLOOR: a member article the Tier-0 classifier
# already called MIXED is known to carry genuine evidence on BOTH sides, so it
# contributes at least this much weighted evidence to each side without
# needing to re-derive/persist the article's internal pos/neg split.
# EVENT_MIXED_MIN_EVIDENCE_FRACTION: each side must account for at least this
# fraction of total weighted evidence before the event itself is called MIXED
# - a small dissenting article against a dominant clear signal should not
# flip the label.
MIXED_ARTICLE_EVIDENCE_FLOOR = 0.3
EVENT_MIXED_MIN_EVIDENCE_FRACTION = 0.2

# --- Dedup gates beyond title similarity (Part 1.2) --------------------------
# titles_are_likely_duplicates() (SequenceMatcher) stays the cheap first-stage
# check. These two are additional gates a candidate must ALSO pass before
# being merged into an existing event - neither alone is sufficient, but both
# together catch the two realistic false-merge modes: an EARNINGS story and a
# REGULATORY story with similarly-worded titles, and two headlines that read
# similarly but cite different amounts ("Rs 8,000 crore" vs "Rs 800 crore").
DEDUP_REQUIRE_SAME_EVENT_TYPE = True
DEDUP_REQUIRE_NUMBER_COMPATIBILITY = True

# --- High-impact escalation gate (Part 1.4) ----------------------------------
# Tier-2 LLM escalation fires when Tier-0 is ambiguous OR the article's
# event_type is inherently high-impact enough to warrant a better read even
# when Tier-0 sounds confident - a headline like "Company faces bankruptcy
# proceedings" isn't lexically ambiguous, but getting it right matters more
# than a routine contract-win headline. Still fully gated behind the caller's
# own allow_llm_escalation=True - the daily scan and RSS poller never pass
# that, so this NEVER fires on the mass 2,300-stock scan regardless of
# event_type.
HIGH_IMPACT_EVENT_TYPES = {
    "EARNINGS", "GUIDANCE", "MNA", "REGULATORY", "LEADERSHIP",
    "FRAUD", "BANKRUPTCY", "CREDIT_RATING", "LEGAL_RULING", "PRODUCT_FAILURE",
}

# --- Stock-level aggregation (spec section 10) -------------------------------
MIN_AGGREGATE_WEIGHT = 0.05  # denominator floor; below this -> insufficient_news, not a fake 0
SENTIMENT_BANDS = [
    (70, 100, "Strongly Bullish"),
    (30, 69, "Bullish"),
    (-29, 29, "Neutral/Mixed"),
    (-69, -30, "Bearish"),
    (-100, -70, "Strongly Bearish"),
]

# --- Momentum / breakdown windows (spec sections 11-12) ----------------------
WINDOW_HOURS = {"1h": 1, "6h": 6, "24h": 24, "7d": 24 * 7}
MOMENTUM_WINDOWS = ("1h", "6h", "24h")  # 7d has no "prior 7d" comparison in V1
MIN_SIGNIFICANT_EVENT_CONFIDENCE = 0.3  # floor for counting toward event velocity

# --- Tier-0 -> Tier-2 escalation gate (spec sections 3, 16) ------------------
# Only articles the lexicon itself flags as genuinely ambiguous are eligible
# for LLM escalation - never a blanket "run the LLM on everything" policy.
# "Ambiguous" means an actual conflict between positive- and negative-signed
# hits landing near zero net - NOT merely one weak same-direction hit (e.g.
# "maintains guidance" is a confident, unambiguous NEUTRAL, not a case that
# needs an LLM's help).
MIXED_ESCALATION_ABS_SCORE = 0.15

# When a negation word ("not", "fails to", ...) flips a lexicon hit's sign,
# the flipped contribution is dampened by this factor rather than mirrored at
# full strength - "not fraudulent" is mild reassurance, not as strongly
# positive as genuine good news is positive.
NEGATION_DAMPEN_FACTOR = 0.3

# --- Tier-2 LLM classifier - OFF by default (spec section 3, 16) ------------
# Same "empty key = not configured" convention as IPO_GURU_API_KEY in main.py.
# Plain REST call (requests.post), no provider SDK, so swapping providers is
# just pointing this URL/payload shape at a different endpoint.
LLM_SENTIMENT_ENABLED = False
LLM_SENTIMENT_API_KEY = ""
LLM_SENTIMENT_API_URL = ""

# --- Caching / worker cadence -------------------------------------------------
NEWS_SENTIMENT_DB_CACHE_SECONDS = 600  # matches the app's existing NEWS_SENTIMENT_CACHE_SECONDS convention
RSS_POLL_SECONDS_MARKET_OPEN = 900
RSS_POLL_SECONDS_MARKET_CLOSED = 1800
