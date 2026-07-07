@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo .venv not found. Please run setup.bat first.
  pause
  exit /b 1
)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env. Please edit it, then run this file again.
  pause
  exit /b 1
)

start "HIT Grade Monitor" /min ".venv\Scripts\python.exe" -u "check_grades.py"
echo HIT Grade Monitor started. Keep the opened browser logged in.
pause
