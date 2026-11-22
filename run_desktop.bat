@echo off
cd /d %~dp0

where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found. Install Python 3.12+ and try again.
  pause
  exit /b 1
)

if not exist .venv (
  echo Creating Python environment...
  python -m venv .venv
)

call .venv\Scripts\activate
python -m pip install -q -r requirements.txt

echo.
echo Starting Asset Tracking desktop...
echo Keep this window open. Close the app window to stop the phone scanner too.
echo Phone and PC must be on the same Wi-Fi.
echo.

python desktop_app.py
if errorlevel 1 pause
