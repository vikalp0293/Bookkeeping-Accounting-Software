@echo off
echo ========================================
echo Sync Accounting QB SDK - Diagnostic Check
echo ========================================
echo.

echo [1] Checking Python process...
tasklist | findstr python
if %ERRORLEVEL% EQU 0 (
    echo ✓ Python process is running
) else (
    echo ✗ Python process NOT running
)
echo.

echo [2] Checking SDK app process...
tasklist | findstr "Sync Accounting"
echo.

echo [3] Checking QuickBooks process...
tasklist | findstr QBW
if %ERRORLEVEL% EQU 0 (
    echo ✓ QuickBooks Desktop is running
) else (
    echo ✗ QuickBooks Desktop NOT running
)
echo.

echo [4] Checking Python installation...
python --version
if %ERRORLEVEL% EQU 0 (
    echo ✓ Python is installed
    where python
) else (
    echo ✗ Python NOT found
)
echo.

echo [5] Finding log files...
echo.
echo Main log location:
echo %APPDATA%\Sync Accounting QB SDK\logs\main.log
echo.
if exist "%APPDATA%\Sync Accounting QB SDK\logs\main.log" (
    echo ✓ Main log exists
    echo.
    echo Last 30 lines of main.log:
    echo ----------------------------------------
    powershell "Get-Content '%APPDATA%\Sync Accounting QB SDK\logs\main.log' -Tail 30"
    echo ----------------------------------------
) else (
    echo ✗ Main log NOT found
    echo Checking alternative locations...
    dir "%LOCALAPPDATA%\Sync Accounting QB SDK\logs\main.log" 2>nul
    dir "%USERPROFILE%\AppData\Roaming\Sync Accounting QB SDK\logs\main.log" 2>nul
)
echo.

echo Sync service log location:
echo %TEMP%\qb-accounting\logs\sync_service.log
echo.
if exist "%TEMP%\qb-accounting\logs\sync_service.log" (
    echo ✓ Sync service log exists
    echo.
    echo Last 30 lines of sync_service.log:
    echo ----------------------------------------
    powershell "Get-Content '%TEMP%\qb-accounting\logs\sync_service.log' -Tail 30"
    echo ----------------------------------------
) else (
    echo ✗ Sync service log NOT found - Python process may not have started
)
echo.

echo ========================================
echo Diagnostic complete
echo ========================================
pause
