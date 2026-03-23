# Windows Troubleshooting Guide - Sync Accounting QB SDK

## Quick Diagnostic Commands

### 1. Check if Python Process is Running

**Command Prompt or PowerShell:**
```cmd
tasklist | findstr python
```

**What to look for:**
- If you see `python.exe` or `pythonw.exe` → Process is running
- If nothing appears → Process failed to start

**More detailed check:**
```cmd
tasklist /FI "IMAGENAME eq python.exe" /FO LIST
```

---

### 2. Check Electron App Process

```cmd
tasklist | findstr "Sync Accounting"
```

Should show: `Sync Accounting QB SDK.exe`

---

### 3. Check QuickBooks Process

```cmd
tasklist | findstr QBW
```

Should show: `QBW32.exe` (QuickBooks Desktop)

---

## Log Files to Check

### A. Electron Main Process Logs (Most Important)

**Location:** `%APPDATA%\Sync Accounting QB SDK\logs\main.log`

**Quick view (last 50 lines):**
```cmd
powershell "Get-Content '%APPDATA%\Sync Accounting QB SDK\logs\main.log' -Tail 50"
```

**Full log:**
```cmd
notepad "%APPDATA%\Sync Accounting QB SDK\logs\main.log"
```

**Open log folder:**
```cmd
explorer "%APPDATA%\Sync Accounting QB SDK\logs"
```

---

### B. Python Sync Service Logs

**Location:** `%TEMP%\qb-accounting\logs\sync_service.log`

**Quick view (last 50 lines):**
```cmd
powershell "Get-Content '%TEMP%\qb-accounting\logs\sync_service.log' -Tail 50"
```

**Full log:**
```cmd
notepad "%TEMP%\qb-accounting\logs\sync_service.log"
```

**Open log folder:**
```cmd
explorer "%TEMP%\qb-accounting\logs"
```

---

### C. Python Installation Logs (if Python was auto-installed)

**Location:** `%TEMP%\python-install.log`

---

## What to Look For in Logs

### ✅ Success Indicators:
```
[INFO] Found 98 queued transactions, auto-starting sync...
[INFO] Starting sync service: python C:\...\sync_runner.py
[INFO] Python version check: Python 3.11.9
[INFO] Starting sync service...
[INFO] Connected to QuickBooks Desktop
[INFO] Found 98 queued transactions
```

### ❌ Common Errors:

**1. Python Not Found:**
```
[ERROR] Python test failed: ...
[ERROR] Python executable not found: python
```
**Fix:** Install Python 3.8+ and ensure it's in PATH

**2. Python Script Not Found:**
```
[ERROR] Python script not found: C:\...\sync_runner.py
```
**Fix:** Reinstall the app

**3. QuickBooks Not Running:**
```
[ERROR] QuickBooks Desktop must be running
[ERROR] Failed to connect to QuickBooks
```
**Fix:** Open QuickBooks Desktop and your company file

**4. Company File Not Found:**
```
[ERROR] Company file not found: C:\...\company.qbw
```
**Fix:** Check company file path in app settings

**5. Process Spawn Failed:**
```
[ERROR] Failed to start Python sync service: spawn python ENOENT
```
**Fix:** Python not in PATH or not installed

---

## Complete Diagnostic Script

Save this as `check-sync-status.bat` and run it:

```batch
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

echo [2] Checking Electron app process...
tasklist | findstr "Sync Accounting"
if %ERRORLEVEL% EQU 0 (
    echo ✓ SDK app is running
) else (
    echo ✗ SDK app NOT running
)
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
python --version 2>nul
if %ERRORLEVEL% EQU 0 (
    echo ✓ Python is installed and in PATH
    python --version
) else (
    echo ✗ Python NOT found in PATH
)
echo.

echo [5] Checking log files...
if exist "%APPDATA%\Sync Accounting QB SDK\logs\main.log" (
    echo ✓ Main log exists
    echo Last 10 lines:
    powershell "Get-Content '%APPDATA%\Sync Accounting QB SDK\logs\main.log' -Tail 10"
) else (
    echo ✗ Main log NOT found
)
echo.

if exist "%TEMP%\qb-accounting\logs\sync_service.log" (
    echo ✓ Sync service log exists
    echo Last 10 lines:
    powershell "Get-Content '%TEMP%\qb-accounting\logs\sync_service.log' -Tail 10"
) else (
    echo ✗ Sync service log NOT found
)
echo.

echo ========================================
echo Diagnostic complete
echo ========================================
pause
```

---

## Step-by-Step Troubleshooting

### Step 1: Verify Python is Installed
```cmd
python --version
```
- If error → Install Python 3.8+
- If shows version → Python is installed

### Step 2: Verify Python is in PATH
```cmd
where python
```
- Should show path like: `C:\Python311\python.exe`
- If not found → Add Python to PATH

### Step 3: Check if Sync Service Started
```cmd
tasklist | findstr python
```
- If python.exe appears → Service is running
- If not → Check logs for error

### Step 4: Check Logs for Errors
```cmd
powershell "Get-Content '%APPDATA%\Sync Accounting QB SDK\logs\main.log' -Tail 30"
```
- Look for `[ERROR]` messages
- Note the exact error message

### Step 5: Verify QuickBooks is Running
```cmd
tasklist | findstr QBW
```
- Should show `QBW32.exe`
- If not → Open QuickBooks Desktop

---

## Common Issues and Solutions

### Issue: "Python test failed"
**Solution:**
1. Install Python 3.8+ from python.org
2. During installation, check "Add Python to PATH"
3. Restart computer
4. Verify: `python --version`

### Issue: "Python script not found"
**Solution:**
1. Reinstall the SDK app
2. Check if app installed correctly

### Issue: "QuickBooks Desktop must be running"
**Solution:**
1. Open QuickBooks Desktop
2. Open your company file (.qbw)
3. Keep QuickBooks open while syncing

### Issue: "Company file not found"
**Solution:**
1. Open SDK app settings
2. Verify company file path is correct
3. Use full path: `C:\Users\...\Company.qbw`

### Issue: Python process starts but immediately exits
**Solution:**
1. Check Python sync service log: `%TEMP%\qb-accounting\logs\sync_service.log`
2. Look for Python errors (syntax errors, import errors, etc.)
3. May need to install Python dependencies manually:
   ```cmd
   cd "%LOCALAPPDATA%\Programs\Sync Accounting QB SDK\resources\python"
   python -m pip install -r requirements.txt
   ```

---

## Getting Help

When reporting issues, provide:
1. Last 30 lines of `main.log`
2. Last 30 lines of `sync_service.log` (if exists)
3. Output of `python --version`
4. Output of `tasklist | findstr python`
5. Whether QuickBooks Desktop is running
6. Company file path (without sensitive info)
