from fastapi import APIRouter, Depends, HTTPException

from news_pipeline import normalize as news_normalize
from news_pipeline import pipeline as news_pipeline

from ..database import SessionLocal
from ..models import UserDB
from ..security import get_current_user
from ..services import market_data
from ..services.ranking import SYMBOL_TO_NAME

router = APIRouter()


@router.get("/api/news-sentiment/{symbol}")
def get_news_sentiment(symbol: str, current_user: UserDB = Depends(get_current_user)):
    """Standalone view of the same news_pipeline breakdown embedded in
    /api/stock/{symbol}'s prediction.news - useful on its own when a caller
    wants the full event/window/momentum detail without the price/candle/
    fundamentals payload. Same on-demand, DB-cached, LLM-escalation-eligible
    path as the stock detail page (never the once-daily full-universe scan)."""
    symbol_upper = symbol.upper()
    company_name = SYMBOL_TO_NAME.get(symbol_upper, symbol_upper)
    try:
        query_symbol = f"{symbol_upper}.NS"
        stock = market_data.get_ticker(query_symbol)
        sector = None
        try:
            sector = market_data.get_info(query_symbol).get("sector")
        except Exception:
            pass

        def fetch_raw_articles():
            return news_normalize.normalize_yfinance_articles(stock.get_news(count=8) or [], source="yfinance_ticker")

        db = SessionLocal()
        try:
            breakdown = news_pipeline.get_or_refresh_stock_sentiment(
                db, symbol_upper, company_name, sector, fetch_raw_articles, allow_llm_escalation=True,
            )
        finally:
            db.close()
        return breakdown
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"News sentiment not available: {str(e)}")
