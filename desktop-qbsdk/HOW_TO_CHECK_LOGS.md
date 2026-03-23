# How to Check Logs for Sync Accounting QB SDK

## Log File Locations

### Electron Main Process Logs
**Location:** `%APPDATA%\Sync Accounting QB SDK\logs\main.log`

**To open:**
1. Press `Win + R`
2. Type: `%APPDATA%\Sync Accounting QB SDK\logs`
3. Press Enter
4. Open `main.log` in Notepad

**Or via Command Prompt:**
```cmd
type "%APPDATA%\Sync Accounting QB SDK\logs\main.log"
```

### Python Sync Service Logs
**Location:** `%TEMP%\qb-accounting\logs\sync_service.log`

**To open:**
1. Press `Win + R`
2. Type: `%TEMP%\qb-accounting\logs`
3. Press Enter
4. Open `sync_service.log` in Notepad

**Or via Command Prompt:**
```cmd
type "%TEMP%\qb-accounting\logs\sync_service.log"
```

## What to Look For

### When Sync Service Starts:
- `"Starting sync service: python ..."`
- `"Python version check: Python 3.x.x"`
- `"Starting sync service..."` (from Python)
- `"Connected to QuickBooks Desktop"`

### Common Errors:
- `"Python test failed"` → Python not installed or not in PATH
- `"Python script not found"` → Script path incorrect
- `"Failed to start Python sync service"` → Python process failed to spawn
- `"QuickBooks Desktop must be running"` → QuickBooks not open
- `"Company file not found"` → Company file path incorrect

## Quick Check Commands

### Check if Python process is running:
```cmd
tasklist | findstr python
```

### Check last 50 lines of main log:
```cmd
powershell "Get-Content '%APPDATA%\Sync Accounting QB SDK\logs\main.log' -Tail 50"
```

### Check last 50 lines of sync service log:
```cmd
powershell "Get-Content '%TEMP%\qb-accounting\logs\sync_service.log' -Tail 50"
```

## In the SDK App

The app sends log messages via IPC events:
- `sync-log` - Normal output from Python process
- `sync-error` - Error messages
- `sync-stopped` - Process stopped

Check the browser console (F12) to see these messages if the UI displays them.
