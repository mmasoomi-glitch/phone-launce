@echo off
title AFAQ Phone Mirror
echo ============================================
echo   AFAQ Phone Mirror - USB Mode
echo ============================================
echo.
echo Make sure your phone is connected via USB
echo and USB Debugging is enabled.
echo.

cd /d "%~dp0"

:: Install dependencies if not already installed
pip show flask >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
)

echo Starting phone mirror server...
echo Open http://localhost:80/phone in your browser
echo (or it will appear in the CRM Phone panel automatically)
echo.
echo Press Ctrl+C to stop.
echo.
python start_usb.py
pause
