"""Background RSS ingestion - matches main.py's existing lifespan /
asyncio.create_task pattern (price_checker_task / market_scan_task /
daily_scan_task). Polls the market-wide RSS feeds, relevance-matches each
article in-memory against every known symbol's alias/sector keywords (cheap
string ops, no network), runs Tier-0 sentiment ONCE PER UNIQUE ARTICLE (via
ingest_articles' sentiment_cache, not once per matched symbol), and persists/
clusters into events for whichever symbols clear the relevance threshold.

Never escalates to Tier-2 (allow_llm_escalation=False, hardcoded) - this is a
background sweep across many symbols at once, the same cost-control reason
the once-daily full-universe scan never uses the pipeline at all.
"""
import datetime

from . import config, pipeline
from .relevance import score_relevance
from .sources import ACTIVE_RSS_SOURCES


def poll_once(db, symbol_directory) -> dict:
    """symbol_directory: list of (symbol, company_name, sector) tuples to
    match RSS articles against - main.py supplies this (its own FULL_NSE_
    SYMBOLS-derived data), so this module never needs to import main.py.
    Returns a small summary dict for logging - not persisted anywhere, just
    printed by the caller."""
    sentiment_cache = {}  # keyed by article url, shared across every symbol this poll touches
    fetched_count = 0
    ingested_per_symbol = {}

    for source in ACTIVE_RSS_SOURCES:
        try:
            articles = source.fetch_news(time_window_hours=config.WINDOW_HOURS["24h"])
        except Exception as exc:
            print(f"news_pipeline RSS poller: {source.name} fetch failed: {exc}")
            continue
        fetched_count += len(articles)

        for symbol, company_name, sector in symbol_directory:
            candidates = [
                a for a in articles
                if score_relevance(symbol, company_name, a["title"], a.get("description", ""), sector)["score"]
                >= config.RELEVANCE_DISCARD_THRESHOLD
            ]
            if not candidates:
                continue
            try:
                accepted = pipeline.ingest_articles(
                    db, symbol, True, company_name, sector, candidates,
                    allow_llm_escalation=False, sentiment_cache=sentiment_cache,
                )
            except Exception as exc:
                print(f"news_pipeline RSS poller: ingest failed for {symbol}: {exc}")
                continue
            if accepted:
                ingested_per_symbol[symbol] = ingested_per_symbol.get(symbol, 0) + accepted

    return {
        "fetched_count": fetched_count,
        "symbols_touched": len(ingested_per_symbol),
        "articles_ingested": sum(ingested_per_symbol.values()),
        "polled_at": datetime.datetime.utcnow().isoformat(),
    }
