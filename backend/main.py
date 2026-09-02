"""Thin entrypoint shim - the real app now lives under app/ (see app/main.py).
Kept as `main.py` so `uvicorn main:app` in start_all.bat/start_server.bat
keeps working with zero changes."""
from app.main import app  # noqa: F401
