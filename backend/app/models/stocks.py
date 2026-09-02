from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship

from ..database import Base


class AlertRuleDB(Base):
    """Threshold price alerts - this table has always been alerting, not a
    plain watchlist, hence the name (the table itself stays "watchlists" so
    no data migration is needed for the rename)."""
    __tablename__ = "watchlists"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    group_id = Column(Integer, ForeignKey("stock_groups.id"), nullable=True)
    symbol = Column(String, index=True)
    upper_threshold = Column(Float, nullable=True)
    lower_threshold = Column(Float, nullable=True)
    alert_triggered = Column(Integer, default=0)

    owner = relationship("UserDB", back_populates="alert_rules")


class StockGroupDB(Base):
    """User-created named folders (e.g. "Banking", "My Picks") for organizing
    tracked stocks/alerts - shared by both the Watchlist and Alerts pages,
    distinguished by group_type. Capped at 10 per user per type, enforced at
    the endpoint (count-then-insert; fine since this is a single-user action,
    not concurrent - not worth a SELECT FOR UPDATE)."""
    __tablename__ = "stock_groups"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    group_type = Column(String, index=True)  # "watchlist" | "alert"
    name = Column(String)


class TrackedStockDB(Base):
    """Plain watchlist entry - just a symbol to keep an eye on, no threshold."""
    __tablename__ = "tracked_stocks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    group_id = Column(Integer, ForeignKey("stock_groups.id"), nullable=True)
    symbol = Column(String, index=True)
