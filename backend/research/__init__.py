"""Offline research tooling - walk-forward backtesting against historical
price data. Deliberately separate from app/ (the live API surface): nothing
in here runs in production or changes what the app serves. It exists to
answer, from history, whether the production heuristic (or a simple
baseline) has ever actually predicted anything - a question app/services/
prediction_tracking.py's live prediction_runs table can only answer slowly,
one real trading day at a time.
"""
