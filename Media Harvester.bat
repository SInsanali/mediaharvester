@echo off
REM Media Harvester - Windows launcher
REM Double-click this file to run the downloader

cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: Python is not installed.
    echo Please install it from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

python mediaharvester.py

echo.
pause
