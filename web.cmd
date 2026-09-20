@echo off
setlocal
chcp 65001 >nul

title GSing Website - http://127.0.0.1:2024
cd /d "%~dp0"

call "C:\Users\23615\miniconda3\Scripts\activate.bat" web_env
if errorlevel 1 (
    echo [ERROR] Failed to activate Conda environment: web_env
    pause
    exit /b 1
)

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "HOST=127.0.0.1"
set "PORT=2024"

echo Starting GSing website...
echo Open http://127.0.0.1:2024 in your browser.
echo Press Ctrl+C to stop the server.
echo.

python -u main.py

if errorlevel 1 (
    echo.
    echo [ERROR] The website stopped unexpectedly.
    pause
)

endlocal
