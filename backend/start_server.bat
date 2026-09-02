@echo off
call .\.venv\Scripts\activate
uvicorn main:app --reload --port 9999