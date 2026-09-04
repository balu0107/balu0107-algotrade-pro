"""Environment-backed configuration. Every value here previously lived as a
hardcoded literal at the top of main.py - the literals below are now only the
LOCAL-DEV FALLBACK, used when the corresponding environment variable isn't
set, so `start_all.bat`/`start_server.bat` keep working with zero setup.

Production must set these via real environment variables - see
`fail_fast_if_unsafe_for_production()`, called once at app startup.
"""
import os

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

_DEV_DATABASE_URL = "postgresql://postgres:superuser@db:5432/stockdemo"
_DEV_SECRET_KEY = "my-awesome-demo-key-198107"

DATABASE_URL = os.getenv("DATABASE_URL", _DEV_DATABASE_URL)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8983513593:AAGA1eA8S-YXHshCgYdivdMdijl_MJkdgEs")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1425739939")
# Free key from ipoguru.in (email ipoguru.in@gmail.com to request one) - the
# IPO tab shows a "not configured" state until this is filled in.
IPO_GURU_API_KEY = os.getenv("IPO_GURU_API_KEY", "")
SECRET_KEY = os.getenv("SECRET_KEY", _DEV_SECRET_KEY)
ALGORITHM = "HS256"

# Manually maintained macro reference (RBI has no simple free live-data API) - update when RBI moves the rate.
RBI_REPO_RATE = {"value_percent": 5.5, "last_updated": "2026-06-06", "note": "Manually maintained reference, not a live feed."}


def fail_fast_if_unsafe_for_production():
    """Called once at app startup. In production, refuses to boot on a
    literal dev secret/credential still in place - better a loud crash at
    startup than a silently insecure deployment."""
    if ENVIRONMENT != "production":
        return
    unsafe = []
    if DATABASE_URL == _DEV_DATABASE_URL:
        unsafe.append("DATABASE_URL is still the local-dev default")
    if SECRET_KEY == _DEV_SECRET_KEY:
        unsafe.append("SECRET_KEY is still the local-dev default")
    if unsafe:
        raise RuntimeError(
            "Refusing to start with ENVIRONMENT=production while: " + "; ".join(unsafe)
            + ". Set real environment variables before deploying."
        )