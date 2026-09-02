"""Periodically fills in prediction_runs' outcome columns for any horizon
that has passed. Hourly is plenty - forward returns don't need to be scored
the instant they mature, and this only ever reads price_history that the
market-scan workers already wrote (no extra yfinance calls of its own)."""
import asyncio

from ..database import SessionLocal
from ..services.prediction_tracking import evaluate_pending_predictions

PREDICTION_EVALUATION_INTERVAL_SECONDS = 3600


def _run_evaluation_once():
    db = SessionLocal()
    try:
        evaluated = evaluate_pending_predictions(db)
        if evaluated:
            print(f"prediction_runs: evaluated {evaluated} matured prediction(s)")
    finally:
        db.close()


async def prediction_evaluation_worker():
    while True:
        try:
            await asyncio.to_thread(_run_evaluation_once)
        except Exception as exc:
            print(f"Prediction evaluation failed: {exc}")
        await asyncio.sleep(PREDICTION_EVALUATION_INTERVAL_SECONDS)
