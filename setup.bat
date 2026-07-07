@echo off
setlocal
cd /d "%~dp0"

echo [1/4] Creating virtual environment...
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m venv .venv
) else (
  python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo Failed to create .venv. Please install Python 3.10 or newer.
  pause
  exit /b 1
)

echo [2/4] Installing Python packages...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Failed to install Python packages.
  pause
  exit /b 1
)

echo [3/4] Installing Playwright Chromium...
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 (
  echo Failed to install Playwright Chromium.
  pause
  exit /b 1
)

echo [4/4] Preparing .env...
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env from .env.example. Please edit .env before running.
) else (
  echo .env already exists.
)

echo Setup finished.
pause
