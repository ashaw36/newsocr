@echo off
cd /d "%~dp0"
set PYTHONUNBUFFERED=1
py -3.11 -m newspaper_app
if errorlevel 1 (
  echo.
  echo Failed to start. Install dependencies with:
  echo   py -3.11 -m pip install -r requirements.txt
  pause
)
