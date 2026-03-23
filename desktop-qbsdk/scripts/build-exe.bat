@echo off
echo Building Sync Accounting Desktop SDK...
echo.

REM Check if Node.js is installed
where node >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Node.js is not installed or not in PATH
    echo Please install Node.js from https://nodejs.org/
    pause
    exit /b 1
)

REM Check if npm is installed
where npm >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: npm is not installed or not in PATH
    pause
    exit /b 1
)

echo Step 1: Installing Node.js dependencies...
call npm install
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to install Node.js dependencies
    pause
    exit /b 1
)

echo.
echo Step 2: Building frontend...
call npm run build:frontend
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to build frontend
    pause
    exit /b 1
)

echo.
echo Step 3: Copying frontend to desktop app...
call npm run copy:frontend
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to copy frontend
    pause
    exit /b 1
)

echo.
echo Step 4: Preparing Python scripts...
call npm run prepare:python
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Python preparation had issues, continuing anyway...
)

echo.
echo Step 5: Building Windows executable...
call npm run build:win
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to build Windows executable
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build complete!
echo ========================================
echo.
echo The installer can be found in: dist\Sync Accounting Desktop SDK Setup *.exe
echo.
echo IMPORTANT: Users must have Python 3.8+ installed on their system.
echo The app will check for Python and prompt to install dependencies if needed.
echo.
pause


