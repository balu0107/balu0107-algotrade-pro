from fastapi import APIRouter, Depends, Query

from ..models import UserDB
from ..security import get_current_user
from ..services.ranking import DAILY_SCAN_UNIVERSE, TOP_PICKS_PER_SECTOR, get_direction_scan

router = APIRouter()


@router.get("/api/top-picks")
def get_top_intraday_picks(direction: str = Query(default="RISE"), current_user: UserDB = Depends(get_current_user)):
    wanted_direction = "FALL" if direction.upper() == "FALL" else "RISE"
    picks, active_timeframe, computed_at = get_direction_scan(wanted_direction)

    sectors = {}
    for pick in picks:
        sectors.setdefault(pick["sector"], [])
        if len(sectors[pick["sector"]]) < TOP_PICKS_PER_SECTOR:
            sectors[pick["sector"]].append(pick)

    # Sectors ordered by their most-liquid pick too, matching the ranking
    # rule for the picks within them.
    sector_groups = [
        {"sector": sector, "picks": sector_picks}
        for sector, sector_picks in sorted(
            sectors.items(),
            key=lambda item: item[1][0]["traded_value"],
            reverse=True,
        )
    ]

    return {
        "direction": wanted_direction,
        "top_overall": picks[:10],
        "sectors": sector_groups,
        "active_timeframe": active_timeframe,
        "total_available": len(picks),
        "scanned_universe_size": len(DAILY_SCAN_UNIVERSE),
        "computed_at": computed_at.isoformat() if computed_at else None,
        "scan_cadence": "daily",
    }


FNO_DISCLAIMER = (
    "This is our own directional algorithm mapped onto options terms, not a real NSE options chain. "
    "The strike is rounded to a plausible interval, not a verified listed strike, and there is no live "
    "premium, open interest, or FII/DII short-positioning data behind it - those require a paid market "
    "data feed that this app does not have access to."
)


def suggest_option_strike(price):
    """Rounds to a plausible NSE strike interval - an approximation, not a verified listed strike."""
    if price < 50: step = 2.5
    elif price < 100: step = 5
    elif price < 500: step = 10
    elif price < 1000: step = 20
    elif price < 2500: step = 50
    else: step = 100
    return round(round(price / step) * step, 2)


def build_option_idea(pick, option_type):
    current_price = pick["current_price"]
    target_price = pick["target_price"]
    reward = abs(target_price - current_price)
    # Risk half the expected reward - a standard risk:reward heuristic, not derived from real option greeks.
    stop_loss_price = round(current_price - reward / 2, 2) if option_type == "CALL" else round(current_price + reward / 2, 2)

    return {
        "symbol": pick["symbol"],
        "sector": pick["sector"],
        "option_type": option_type,
        "current_price": current_price,
        "suggested_strike": suggest_option_strike(current_price),
        "target_underlying_price": target_price,
        "stop_loss_underlying_price": stop_loss_price,
        "expected_change_percent": pick["expected_change_percent"],
        "confidence_percent": pick["confidence_percent"],
        "traded_value": pick["traded_value"],
    }


@router.get("/api/fno-ideas")
def get_fno_ideas(option_type: str = Query(default="CALL"), current_user: UserDB = Depends(get_current_user)):
    wanted_option_type = "PUT" if option_type.upper() == "PUT" else "CALL"
    wanted_direction = "FALL" if wanted_option_type == "PUT" else "RISE"
    picks, active_timeframe, computed_at = get_direction_scan(wanted_direction)

    ideas = [build_option_idea(pick, wanted_option_type) for pick in picks]

    sectors = {}
    for idea in ideas:
        sectors.setdefault(idea["sector"], [])
        if len(sectors[idea["sector"]]) < TOP_PICKS_PER_SECTOR:
            sectors[idea["sector"]].append(idea)

    # Sectors ordered by their most-liquid idea too, matching the ranking
    # rule for the ideas within them.
    sector_groups = [
        {"sector": sector, "picks": sector_picks}
        for sector, sector_picks in sorted(
            sectors.items(),
            key=lambda item: item[1][0]["traded_value"],
            reverse=True,
        )
    ]

    return {
        "option_type": wanted_option_type,
        "top_overall": ideas[:10],
        "sectors": sector_groups,
        "active_timeframe": active_timeframe,
        "total_available": len(ideas),
        "scanned_universe_size": len(DAILY_SCAN_UNIVERSE),
        "computed_at": computed_at.isoformat() if computed_at else None,
        "scan_cadence": "daily",
        "disclaimer": FNO_DISCLAIMER,
    }
