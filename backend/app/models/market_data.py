from sqlalchemy import Column, Integer, String, Float, DateTime

from ..database import Base


class PriceHistoryDB(Base):
    """Our own OHLCV snapshots, saved every market-scan cycle for the whole
    NSE_SYMBOLS universe - piggybacks on data the scan already fetches, so it
    costs no extra yfinance calls. Gives us a durable, app-owned dataset to
    backtest against or eventually train a model on, instead of only ever
    trusting whatever yfinance returns live in the moment."""
    __tablename__ = "price_history"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    recorded_at = Column(DateTime, index=True)
    open = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=True)
    volume = Column(Integer, nullable=True)
