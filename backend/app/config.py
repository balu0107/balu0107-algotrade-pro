"""Environment-backed configuration. All sensitive tokens and connection strings 
are fully parameterized via environment variables for cloud deployment.
"""
import os

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

_DEV_DATABASE_URL = "postgresql://postgres:superuser@db:5432/stockdemo"
_DEV_SECRET_KEY = "my-awesome-demo-key-198107"

DATABASE_URL = os.getenv("DATABASE_URL", _DEV_DATABASE_URL)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
IPO_GURU_API_KEY = os.getenv("IPO_GURU_API_KEY", "")
SECRET_KEY = os.getenv("SECRET_KEY", _DEV_SECRET_KEY)
ALGORITHM = "HS256"

RBI_REPO_RATE = {"value_percent": 5.5, "last_updated": "2026-06-06", "note": "Manually maintained reference, not a live feed."}


def fail_fast_if_unsafe_for_production():
    """Refuses to boot in production if default dev credentials or missing secrets are detected."""
    if ENVIRONMENT != "production":
        return
    unsafe = []
    if DATABASE_URL == _DEV_DATABASE_URL:
        unsafe.append("DATABASE_URL is still the local-dev default")
    if SECRET_KEY == _DEV_SECRET_KEY:
        unsafe.append("SECRET_KEY is still the local-dev default")
    if not TELEGRAM_BOT_TOKEN:
        unsafe.append("TELEGRAM_BOT_TOKEN is missing")
    if unsafe:
        raise RuntimeError(
            "Refusing to start with ENVIRONMENT=production while: " + "; ".join(unsafe)
            + ". Set real environment variables before deploying."
        )