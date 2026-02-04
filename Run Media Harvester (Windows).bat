@echo off
title Media Harvester
REM Media Harvester - Windows launcher
REM Double-click this file to run the downloader

cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo ========================================
    echo   Python is not installed!
    echo ========================================
    echo.
    echo Please install Python from:
    echo   https://www.python.org/downloads/
    echo.
    echo IMPORTANT: Check "Add Python to PATH" during installation
    echo.
    pause
    exit /b 1
)

python mediaharvester.py

echo.
pause
