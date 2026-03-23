@echo off
echo Installing Python dependencies for QB Accounting SDK...
echo.

REM Check if Python is installed
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)

REM Get the directory where this script is located
set SCRIPT_DIR=%~dp0
set PYTHON_DIR=%SCRIPT_DIR%python

echo Installing dependencies from %PYTHON_DIR%...
cd /d "%PYTHON_DIR%"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Python dependencies installed successfully!
) else (
    echo.
    echo ERROR: Failed to install Python dependencies
    pause
    exit /b 1
)
