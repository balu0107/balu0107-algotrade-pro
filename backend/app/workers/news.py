"""Background RSS-poll worker. Moved verbatim from main.py (Phase 2A, no
behavior change)."""
import asyncio

from news_pipeline import config as news_config
from news_pipeline import worker as news_worker

from ..database import SessionLocal
from ..services.prediction import is_market_open_now
from ..services.ranking import FULL_NSE_SYMBOLS, _daily_scan_cache


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
