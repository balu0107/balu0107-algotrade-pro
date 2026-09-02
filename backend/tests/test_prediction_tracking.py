"""Tests for prediction_runs: recording what the daily scan predicted, and
evaluating those predictions against forward returns once their horizon has
passed. Uses an in-memory SQLite DB (Base.metadata is plain SQLAlchemy, no
Postgres-specific features here) - same pattern as tests/test_sentiment.py's
pipeline-integration section.

Run from backend/: `.venv/Scripts/python.exe -m pytest tests/test_prediction_tracking.py -v`
"""
import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.market_data import PriceHistoryDB
from app.models.predictions import PredictionRunDB
from app.services.prediction_tracking import (
    evaluate_pending_predictions,
    next_trading_day,
    record_daily_predictions,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[PriceHistoryDB.__table__, PredictionRunDB.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def make_scan_result(symbol="RELIANCE", direction="RISE", current_price=1000.0, **overrides):
    result = {
        "symbol": symbol, "sector": "Energy", "current_price": current_price,
        "direction": direction, "target_price": current_price * 1.02,
        "expected_change_percent": 2.0, "confidence_percent": 70, "rise_probability": 65,
        "traded_value": 6_00_00_00_000,
    }
    result.update(overrides)
    return result


# --- next_trading_day: weekend skipping ---------------------------------

def test_next_trading_day_skips_weekend():
    friday = datetime.date(2026, 8, 21)  # a Friday
    assert next_trading_day(friday, 1) == datetime.date(2026, 8, 24)  # Monday, not Saturday


def test_next_trading_day_five_days_ahead_spans_one_weekend():
    monday = datetime.date(2026, 8, 24)
    assert next_trading_day(monday, 5) == datetime.date(2026, 8, 31)  # next Monday


# --- record_daily_predictions --------------------------------------------

def test_records_one_row_per_symbol(db_session):
    results = [make_scan_result("RELIANCE"), make_scan_result("TCS", direction="FALL")]
    inserted = record_daily_predictions(db_session, results, "DELIVERY", datetime.date(2026, 8, 21))
    assert inserted == 2
    rows = db_session.query(PredictionRunDB).all()
    assert {r.symbol for r in rows} == {"RELIANCE", "TCS"}
    reliance = next(r for r in rows if r.symbol == "RELIANCE")
    assert reliance.predicted_direction == "RISE"
    assert reliance.price_at_generation == 1000.0
    assert reliance.horizon_1d_target_date == datetime.date(2026, 8, 24)  # Friday -> Monday
    assert reliance.horizon_5d_target_date == datetime.date(2026, 8, 28)  # Friday + 5 trading days
    assert reliance.horizon_1d_evaluated_at is None
    assert reliance.horizon_1d_actual_return_percent is None


def test_calling_twice_for_the_same_day_does_not_duplicate_or_overwrite(db_session):
    """A restart re-triggering the daily scan for a day already recorded must
    not create a second row or touch the first one's values - this is the
    entry point for the whole table's immutability guarantee."""
    day = datetime.date(2026, 8, 21)
    record_daily_predictions(db_session, [make_scan_result("RELIANCE", current_price=1000.0)], "DELIVERY", day)
    second_insert = record_daily_predictions(
        db_session, [make_scan_result("RELIANCE", current_price=9999.0)], "DELIVERY", day,
    )
    assert second_insert == 0
    rows = db_session.query(PredictionRunDB).filter(PredictionRunDB.symbol == "RELIANCE").all()
    assert len(rows) == 1
    assert rows[0].price_at_generation == 1000.0  # untouched by the second call


def test_different_days_for_the_same_symbol_both_get_recorded(db_session):
    record_daily_predictions(db_session, [make_scan_result("RELIANCE")], "DELIVERY", datetime.date(2026, 8, 21))
    record_daily_predictions(db_session, [make_scan_result("RELIANCE")], "DELIVERY", datetime.date(2026, 8, 24))
    rows = db_session.query(PredictionRunDB).filter(PredictionRunDB.symbol == "RELIANCE").all()
    assert len(rows) == 2


# --- evaluate_pending_predictions ----------------------------------------

def _seed_price_history(db_session, symbol, recorded_at, close):
    db_session.add(PriceHistoryDB(symbol=symbol, recorded_at=recorded_at, open=close, high=close, low=close, close=close, volume=1000))
    db_session.commit()


def test_correct_rise_prediction_is_scored_correct(db_session):
    prediction_day = datetime.date(2026, 8, 21)
    record_daily_predictions(db_session, [make_scan_result("RELIANCE", direction="RISE", current_price=1000.0)], "DELIVERY", prediction_day)
    target_date = next_trading_day(prediction_day, 1)
    _seed_price_history(db_session, "RELIANCE", datetime.datetime.combine(target_date, datetime.time(15, 30)), 1050.0)

    evaluated = evaluate_pending_predictions(db_session, today=target_date)
    assert evaluated >= 1
    row = db_session.query(PredictionRunDB).filter(PredictionRunDB.symbol == "RELIANCE").one()
    assert row.horizon_1d_actual_price == 1050.0
    assert row.horizon_1d_actual_return_percent == pytest.approx(5.0)
    assert row.horizon_1d_direction_correct is True
    assert row.horizon_1d_evaluated_at is not None
    # 5-day horizon hasn't arrived yet - must stay untouched
    assert row.horizon_5d_evaluated_at is None


def test_wrong_direction_prediction_is_scored_incorrect(db_session):
    prediction_day = datetime.date(2026, 8, 21)
    record_daily_predictions(db_session, [make_scan_result("TCS", direction="RISE", current_price=1000.0)], "DELIVERY", prediction_day)
    target_date = next_trading_day(prediction_day, 1)
    _seed_price_history(db_session, "TCS", datetime.datetime.combine(target_date, datetime.time(15, 30)), 950.0)

    evaluate_pending_predictions(db_session, today=target_date)
    row = db_session.query(PredictionRunDB).filter(PredictionRunDB.symbol == "TCS").one()
    assert row.horizon_1d_direction_correct is False


def test_sideways_prediction_correct_only_within_tolerance(db_session):
    prediction_day = datetime.date(2026, 8, 21)
    record_daily_predictions(db_session, [make_scan_result("INFY", direction="SIDEWAYS", current_price=1000.0)], "DELIVERY", prediction_day)
    target_date = next_trading_day(prediction_day, 1)
    _seed_price_history(db_session, "INFY", datetime.datetime.combine(target_date, datetime.time(15, 30)), 1003.0)  # +0.3%, inside tolerance

    evaluate_pending_predictions(db_session, today=target_date)
    row = db_session.query(PredictionRunDB).filter(PredictionRunDB.symbol == "INFY").one()
    assert row.horizon_1d_direction_correct is True


def test_no_matching_price_history_leaves_prediction_pending(db_session):
    """No snapshot yet for the target date (e.g. the scan hasn't run that far
    forward) - must skip cleanly and retry later, not error or guess."""
    prediction_day = datetime.date(2026, 8, 21)
    record_daily_predictions(db_session, [make_scan_result("WIPRO")], "DELIVERY", prediction_day)
    target_date = next_trading_day(prediction_day, 1)

    evaluated = evaluate_pending_predictions(db_session, today=target_date)
    assert evaluated == 0
    row = db_session.query(PredictionRunDB).filter(PredictionRunDB.symbol == "WIPRO").one()
    assert row.horizon_1d_evaluated_at is None


def test_already_evaluated_row_is_never_touched_again(db_session):
    """The core immutability guarantee: once an outcome is recorded, a
    second evaluate_pending_predictions() call - even with different price
    data available - must not change it."""
    prediction_day = datetime.date(2026, 8, 21)
    record_daily_predictions(db_session, [make_scan_result("HDFCBANK", direction="RISE", current_price=1000.0)], "DELIVERY", prediction_day)
    target_date = next_trading_day(prediction_day, 1)
    _seed_price_history(db_session, "HDFCBANK", datetime.datetime.combine(target_date, datetime.time(15, 30)), 1050.0)
    evaluate_pending_predictions(db_session, today=target_date)

    row = db_session.query(PredictionRunDB).filter(PredictionRunDB.symbol == "HDFCBANK").one()
    first_result = row.horizon_1d_actual_return_percent
    first_evaluated_at = row.horizon_1d_evaluated_at

    # A later, wildly different snapshot shows up for the same date - must not retroactively change the score.
    _seed_price_history(db_session, "HDFCBANK", datetime.datetime.combine(target_date, datetime.time(15, 35)), 500.0)
    evaluate_pending_predictions(db_session, today=target_date)

    row = db_session.query(PredictionRunDB).filter(PredictionRunDB.symbol == "HDFCBANK").one()
    assert row.horizon_1d_actual_return_percent == first_result
    assert row.horizon_1d_evaluated_at == first_evaluated_at


def test_horizon_not_yet_reached_is_not_evaluated(db_session):
    prediction_day = datetime.date(2026, 8, 21)
    record_daily_predictions(db_session, [make_scan_result("SBIN")], "DELIVERY", prediction_day)
    # "today" is still the prediction day itself - the 1d horizon hasn't arrived yet.
    evaluated = evaluate_pending_predictions(db_session, today=prediction_day)
    assert evaluated == 0
