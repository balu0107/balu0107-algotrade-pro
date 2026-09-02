"""Records what the daily market scan actually predicted, then later checks
those predictions against what actually happened - the prediction_runs
table this all writes to is never overwritten (see app/models/predictions.py
for how that's enforced). This is the data foundation every future
backtesting/ranking-rework effort needs; nothing here changes what the app
shows a user today.

Forward-return horizons are trading days, not calendar days (Saturday/Sunday
skipped) - there is no NSE holiday calendar wired in, so a holiday just means
that day's price_history snapshot won't exist yet when evaluation runs; it
naturally retries on the next cycle until a later trading day's snapshot
appears. Documented simplification, not a correctness bug.
"""
import datetime

from ..models.market_data import PriceHistoryDB
from ..models.predictions import PREDICTION_MODEL_VERSION, PredictionRunDB

HORIZON_TRADING_DAYS = {"1d": 1, "5d": 5}
# A predicted SIDEWAYS call counts as correct if the actual move stayed
# inside this band - anything wider means the stock clearly moved one way or
# the other and "sideways" missed it.
SIDEWAYS_TOLERANCE_PERCENT = 0.5


def ist_today():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)).date()


def next_trading_day(start_date, trading_days_ahead):
    current = start_date
    remaining = trading_days_ahead
    while remaining > 0:
        current += datetime.timedelta(days=1)
        if current.weekday() < 5:  # Saturday=5, Sunday=6
            remaining -= 1
    return current


def record_daily_predictions(db, results, active_timeframe, prediction_date):
    """Inserts one row per symbol the daily scan evaluated, skipping any
    symbol that already has a row for this date - safe to call more than
    once for the same day (e.g. a restart re-triggering the scan) without
    creating duplicates or touching an already-written row."""
    if not results:
        return 0

    already_recorded = {
        row[0]
        for row in db.query(PredictionRunDB.symbol)
        .filter(PredictionRunDB.prediction_date == prediction_date)
        .all()
    }
    generated_at = datetime.datetime.utcnow()
    horizon_1d_target = next_trading_day(prediction_date, HORIZON_TRADING_DAYS["1d"])
    horizon_5d_target = next_trading_day(prediction_date, HORIZON_TRADING_DAYS["5d"])

    inserted = 0
    for item in results:
        symbol = item.get("symbol")
        if not symbol or symbol in already_recorded:
            continue
        db.add(PredictionRunDB(
            symbol=symbol,
            prediction_date=prediction_date,
            generated_at=generated_at,
            model_version=PREDICTION_MODEL_VERSION,
            timeframe=active_timeframe,
            price_at_generation=item["current_price"],
            predicted_direction=item["direction"],
            rise_probability=item.get("rise_probability"),
            confidence_percent=item.get("confidence_percent"),
            expected_change_percent=item.get("expected_change_percent"),
            target_price=item.get("target_price"),
            traded_value=item.get("traded_value"),
            sector=item.get("sector"),
            horizon_1d_target_date=horizon_1d_target,
            horizon_5d_target_date=horizon_5d_target,
        ))
        inserted += 1

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"prediction_runs insert failed, skipping today's persistence: {exc}")
        return 0
    return inserted


def direction_correct(predicted_direction, return_percent):
    if predicted_direction == "RISE":
        return return_percent > 0
    if predicted_direction == "FALL":
        return return_percent < 0
    return abs(return_percent) <= SIDEWAYS_TOLERANCE_PERCENT


def _find_actual_close(db, symbol, on_or_after_date):
    """First price_history snapshot on/after the target date - reuses data
    the market scan already wrote (no extra yfinance calls). Returns None
    if that day hasn't been scanned yet, so the caller can just retry later."""
    cutoff = datetime.datetime.combine(on_or_after_date, datetime.time.min)
    row = (
        db.query(PriceHistoryDB)
        .filter(PriceHistoryDB.symbol == symbol, PriceHistoryDB.recorded_at >= cutoff, PriceHistoryDB.close.isnot(None))
        .order_by(PriceHistoryDB.recorded_at.asc())
        .first()
    )
    return row.close if row else None


def _evaluate_horizon(db, pending_runs, horizon_key):
    target_date_col = f"horizon_{horizon_key}_target_date"
    evaluated_at_col = f"horizon_{horizon_key}_evaluated_at"
    evaluated = 0
    for run in pending_runs:
        if getattr(run, evaluated_at_col) is not None:
            continue
        target_date = getattr(run, target_date_col)
        actual_close = _find_actual_close(db, run.symbol, target_date)
        if actual_close is None:
            continue
        return_percent = (actual_close - run.price_at_generation) / run.price_at_generation * 100
        setattr(run, f"horizon_{horizon_key}_actual_price", actual_close)
        setattr(run, f"horizon_{horizon_key}_actual_return_percent", round(return_percent, 3))
        setattr(run, f"horizon_{horizon_key}_direction_correct", direction_correct(run.predicted_direction, return_percent))
        setattr(run, evaluated_at_col, datetime.datetime.utcnow())
        evaluated += 1
    return evaluated


def evaluate_pending_predictions(db, today=None):
    """Fills in the outcome columns for any prediction whose horizon has
    passed and whose outcome hasn't been recorded yet. Structurally can't
    rewrite an already-evaluated row: the query filters on `..._evaluated_at
    IS NULL`, so a row that already has an outcome never comes back out of
    this query again, regardless of how many times or how often this runs."""
    today = today or ist_today()
    total_evaluated = 0

    for horizon_key in HORIZON_TRADING_DAYS:
        target_date_col = getattr(PredictionRunDB, f"horizon_{horizon_key}_target_date")
        evaluated_at_col = getattr(PredictionRunDB, f"horizon_{horizon_key}_evaluated_at")
        pending = (
            db.query(PredictionRunDB)
            .filter(evaluated_at_col.is_(None), target_date_col.isnot(None), target_date_col <= today)
            .all()
        )
        total_evaluated += _evaluate_horizon(db, pending, horizon_key)

    if total_evaluated:
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            print(f"prediction_runs evaluation commit failed: {exc}")
            return 0
    return total_evaluated
