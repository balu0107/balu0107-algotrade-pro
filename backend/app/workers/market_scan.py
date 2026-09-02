"""Background market-scan warmers. Moved verbatim from main.py (Phase 2A, no
behavior change)."""
import asyncio

from ..services.prediction import is_market_open_now
from ..services.ranking import TOP_PICKS_CACHE_SECONDS, get_daily_market_scan, get_market_scan


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
