"""App assembly only: FastAPI() instance, CORS, the catch-all exception
handler, lifespan (background workers), and router registration. No business
logic lives here - every route delegates to services/, every route file
lives under api/.
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config
from .database import init_db
from . import models  # noqa: F401 - import registers every model on Base.metadata before init_db()
from .security import seed_default_user
from .workers.alerts import proactive_price_checker
from .workers.market_scan import daily_scan_warmer, market_scan_warmer
from .workers.news import news_rss_poller
from .workers.prediction_evaluation import prediction_evaluation_worker

from .api import alerts, auth, ipos, news, predictions, stocks, watchlist


@asynccontextmanager
async def lifespan(app: FastAPI):
    price_checker_task = asyncio.create_task(proactive_price_checker())
    market_scan_task = asyncio.create_task(market_scan_warmer())
    daily_scan_task = asyncio.create_task(daily_scan_warmer())
    news_rss_task = asyncio.create_task(news_rss_poller())
    prediction_evaluation_task = asyncio.create_task(prediction_evaluation_worker())
    yield
    price_checker_task.cancel()
    market_scan_task.cancel()
    news_rss_task.cancel()
    daily_scan_task.cancel()
    prediction_evaluation_task.cancel()


config.fail_fast_if_unsafe_for_production()
init_db()
seed_default_user()

app = FastAPI(lifespan=lifespan)


@app.exception_handler(Exception)
async def catch_all_errors(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": f"THE REAL ERROR IS: {repr(exc)}"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(stocks.router)
app.include_router(predictions.router)
app.include_router(news.router)
app.include_router(watchlist.router)
app.include_router(alerts.router)
app.include_router(ipos.router)
