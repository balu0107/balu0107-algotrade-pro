"""Importing this package registers every model class on database.Base's
metadata - `from app import models` (or importing any of the submodules
directly) must happen before database.init_db() is called."""
from .users import UserDB
from .stocks import AlertRuleDB, StockGroupDB, TrackedStockDB
from .market_data import PriceHistoryDB
from .predictions import PredictionRunDB

__all__ = ["UserDB", "AlertRuleDB", "StockGroupDB", "TrackedStockDB", "PriceHistoryDB", "PredictionRunDB"]
