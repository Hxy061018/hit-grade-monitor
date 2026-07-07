@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo .venv not found. Please run setup.bat first.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" "check_grades.py" --refresh-cache
pause
