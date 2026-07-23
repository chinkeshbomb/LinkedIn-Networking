@echo off
title LinkedIn Automator
cd /d "%~dp0"

echo ========================================
echo   LinkedIn Automator - Starting...
echo ========================================
echo.

:: Check Python
python --version 2>nul
if errorlevel 1 (
    python3 --version 2>nul
    if errorlevel 1 (
        echo ERROR: Python not found. Install from python.org
        pause
        exit /b 1
    )
)

:: Create venv if needed
if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv venv
)

:: Activate venv
call "venv\Scripts\activate.bat"

:: Install deps if needed
python -c "import flask" 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    pip install --upgrade pip
    pip install -r requirements.txt
)

:: Launch Chrome with debugging
echo Launching Chrome with debugging...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir="%cd%\chrome_profile" --no-first-run --no-default-browser-check https://www.linkedin.com

echo Waiting for Chrome...
timeout /t 4 /nobreak >nul

echo.
echo Chrome running on port 9222
echo FIRST TIME: Log in to LinkedIn in Chrome.
echo Open http://localhost:5000
echo.

python app.py

echo.
echo App stopped.
pause
