from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String, UniqueConstraint

from ..database import Base

# Bumped whenever build_algo_prediction's scoring formula changes materially -
# stamped on every row so a backtest can separate "the v1 heuristic underperformed"
# from "we changed the formula partway through the sample." No versioning
# *system* yet (that's the deferred model-registry roadmap item) - this is
# just an honest label on data collected under the current formula.
PREDICTION_MODEL_VERSION = "heuristic-v1"


class PredictionRunDB(Base):
    """One immutable row per (symbol, trading day) the daily market scan
    evaluated - a permanent record of what was actually predicted, so it can
    be checked later against what actually happened. This is the dataset
    every future backtest/model-comparison/ranking-rework effort reads from;
    without it there is no way to know whether any of this beats a coin flip.

    Deliberately NOT scoped to just the symbols shown in Top Picks/Falls/F&O -
    every symbol the daily scan evaluated (regardless of direction) gets a
    row, so later analysis isn't limited to a survivorship-biased "what we
    happened to show someone" subset.

    Immutability is enforced structurally, not by convention: the outcome
    columns start NULL and evaluate_pending_predictions() only ever touches
    rows still matching `..._evaluated_at IS NULL` in its own query filter -
    a row that has already been scored can never be re-scored, even if the
    prediction algorithm changes later.
    """
    __tablename__ = "prediction_runs"
    __table_args__ = (
        UniqueConstraint("symbol", "prediction_date", name="uq_prediction_runs_symbol_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    prediction_date = Column(Date, index=True, nullable=False)  # IST calendar date the daily scan ran
    generated_at = Column(DateTime, nullable=False)
    model_version = Column(String, nullable=False, default=PREDICTION_MODEL_VERSION)
    timeframe = Column(String, nullable=False)  # INTRADAY or DELIVERY - whichever the scan used that day

    price_at_generation = Column(Float, nullable=False)
    predicted_direction = Column(String, nullable=False)  # RISE / FALL / SIDEWAYS
    rise_probability = Column(Float, nullable=True)
    confidence_percent = Column(Float, nullable=True)
    expected_change_percent = Column(Float, nullable=True)
    target_price = Column(Float, nullable=True)
    traded_value = Column(Float, nullable=True)
    sector = Column(String, nullable=True)

    horizon_1d_target_date = Column(Date, nullable=True)
    horizon_1d_actual_price = Column(Float, nullable=True)
    horizon_1d_actual_return_percent = Column(Float, nullable=True)
    horizon_1d_direction_correct = Column(Boolean, nullable=True)
    horizon_1d_evaluated_at = Column(DateTime, nullable=True)

    horizon_5d_target_date = Column(Date, nullable=True)
    horizon_5d_actual_price = Column(Float, nullable=True)
    horizon_5d_actual_return_percent = Column(Float, nullable=True)
    horizon_5d_direction_correct = Column(Boolean, nullable=True)
    horizon_5d_evaluated_at = Column(DateTime, nullable=True)
