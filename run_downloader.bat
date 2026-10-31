@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python was not found.
    echo Please install Python 3.10 or newer from https://www.python.org/downloads/
    echo Then run this file again.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating a private Python environment...
    py -3 -m venv .venv
    if errorlevel 1 (
        echo.
        echo Could not create the Python environment.
        echo Make sure Python 3.10 or newer is installed correctly.
        pause
        exit /b 1
    )
)

echo Checking required packages...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Could not install the required packages.
    pause
    exit /b 1
)

echo.
echo Starting Steam Screenshot Archiver...
".venv\Scripts\python.exe" steam_screenshot_archiver.py
if errorlevel 1 (
    echo.
    echo The downloader exited with an error.
)
echo.
pause
