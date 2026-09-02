"""DB models for the news-sentiment pipeline.

Deliberately its own declarative Base (NewsBase), bound to the app's existing
engine, rather than main.py's Base - the only link back to existing tables is
a plain `symbol` string (never an ORM relationship), so there's no need to
import main.py's models here, which would risk a circular import. main.py just
calls `NewsBase.metadata.create_all(bind=engine)` once, right next to its own
`Base.metadata.create_all(bind=engine)`.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, UniqueConstraint, Index
from sqlalchemy.orm import declarative_base

NewsBase = declarative_base()


class ArticleDB(NewsBase):
    """One row per fetched article, after normalization. Kept even for
    articles that get discarded for low relevance or rolled into an event as a
    duplicate - this is the audit trail that makes "why did this stock get
    +67" answerable after the fact."""
    __tablename__ = "news_articles"
    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, index=True)
    source_url = Column(String, index=True)                       # NOT globally unique - see uq_article_url_entity below
    title = Column(String)
    description = Column(Text, nullable=True)
    published_at = Column(DateTime, index=True)
    fetched_at = Column(DateTime)
    symbol = Column(String, nullable=True, index=True)          # NSE symbol when known
    company_query = Column(String, nullable=True, index=True)   # free-text name for no-ticker (IPO) lookups
    title_hash = Column(String, index=True)                     # normalized-title hash, cheap dup pre-filter
    relevance_score = Column(Float, nullable=True)
    sentiment_score = Column(Float, nullable=True)               # [-1, 1]
    sentiment_label = Column(String, nullable=True)              # POSITIVE | NEUTRAL | NEGATIVE | MIXED
    sentiment_tier = Column(String, nullable=True)               # "lexicon" | "llm" - debuggability
    discarded_reason = Column(String, nullable=True)             # e.g. "low_relevance" - kept, not deleted
    created_at = Column(DateTime)

    # relevance_score is inherently a property of (article, symbol) - one
    # market-wide RSS story (e.g. "oil companies rally") is legitimately
    # relevant to several symbols at once, each getting its own row/score, so
    # the same source_url appears more than once on purpose. What's NOT
    # allowed is re-ingesting the identical (url, symbol) pair twice.
    __table_args__ = (UniqueConstraint("source_url", "symbol", "company_query", name="uq_article_url_entity"),)


class EventDB(NewsBase):
    """The deduplicated unit multiple outlets covering the same story collapse
    into. Independently identifiable from its member articles - it carries its
    own sentiment/confidence, not a value derived fresh every read."""
    __tablename__ = "news_events"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=True, index=True)
    company_query = Column(String, nullable=True, index=True)
    event_cluster_key = Column(String, index=True)   # dedup key articles were matched against
    event_type = Column(String, index=True)           # EARNINGS | GUIDANCE | CONTRACT_WIN | REGULATORY | ...
    event_summary = Column(String)                     # best (highest source-weight) member article's title
    event_timestamp = Column(DateTime, index=True)      # earliest member article
    last_seen_at = Column(DateTime, index=True)          # latest member article
    sentiment_score = Column(Float)                      # weighted aggregate across member articles, [-1, 1]
    sentiment_label = Column(String)
    confidence = Column(Float)                           # [0, CONFIDENCE_CAP]
    relevance = Column(Float, default=0.0)                # best member article's relevance - feeds stock-level event_weight
    article_count = Column(Integer, default=1)
    unique_source_count = Column(Integer, default=1)

    __table_args__ = (Index("ix_news_events_symbol_time", "symbol", "event_timestamp"),)


class ArticleEventMapDB(NewsBase):
    """Article <-> event mapping. V1 always populates this 1:N (each article
    belongs to exactly one event) - kept as its own table per the requested
    schema so a future relaxation to genuinely multi-event articles needs no
    schema change, just a new row."""
    __tablename__ = "news_article_event_map"
    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("news_articles.id"), index=True)
    event_id = Column(Integer, ForeignKey("news_events.id"), index=True)
    is_primary_event = Column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("article_id", "event_id", name="uq_article_event"),)


class SentimentScoreCacheDB(NewsBase):
    """Per-symbol read cache of the four breakdown windows - refreshed on a
    TTL, upserted (not appended). Momentum does NOT depend on this table's own
    history; it's recomputed directly from news_events timestamps each time,
    so this table never needs to grow into a time series."""
    __tablename__ = "news_sentiment_cache"
    symbol = Column(String, primary_key=True)
    score_1h = Column(Float, nullable=True)
    confidence_1h = Column(Float, nullable=True)
    score_6h = Column(Float, nullable=True)
    confidence_6h = Column(Float, nullable=True)
    score_24h = Column(Float, nullable=True)
    confidence_24h = Column(Float, nullable=True)
    score_7d = Column(Float, nullable=True)
    confidence_7d = Column(Float, nullable=True)
    article_count_24h = Column(Integer, default=0)
    event_count_24h = Column(Integer, default=0)
    computed_at = Column(DateTime, index=True)
