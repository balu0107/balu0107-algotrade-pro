@echo off
setlocal
cd /d "%~dp0"

start "Backend (port 9999)" cmd /k "cd backend && call .venv\Scripts\activate && uvicorn main:app --reload --port 9999"

REM cmd's default "node" on this machine is v16, too old for Next.js 16 (needs
REM 20.9+). "nvm use" would fix that machine-wide but requires admin rights
REM (confirmed: fails with "Access is denied" un-elevated) - so instead this
REM just puts the v20 install first on PATH for this one window only. This
REM path is specific to this machine, not portable - matches how DATABASE_URL
REM etc. are hardcoded constants elsewhere in this project.
start "Frontend (port 3000)" cmd /k "set PATH=C:\Users\satya\AppData\Roaming\nvm\v20.20.2;%PATH% && cd frontend && npm run dev"

echo Backend and frontend are starting in separate windows.
echo Close each window (or Ctrl+C inside it) to stop that server.
endlocal
