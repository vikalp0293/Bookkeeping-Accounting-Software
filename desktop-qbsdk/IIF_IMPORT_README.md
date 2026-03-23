# IIF Auto-Import Feature

This folder contains functionality to automatically import IIF files into QuickBooks Desktop using the QuickBooks SDK.

## Overview

The IIF import automation allows you to:
1. Download IIF files from the backend API
2. Automatically import them into QuickBooks Desktop
3. No manual steps required!

## Files Created

### Core Modules

1. **`python/iif_importer.py`**
   - `IIFImporter` class - Handles IIF file import via QuickBooks SDK
   - Tries multiple methods:
     - SDK `ImportData` method (preferred)
     - qbXML import (fallback)
     - UI automation (last resort)

2. **`python/iif_auto_sync.py`**
   - `IIFAutoSync` class - Automatically downloads and imports IIF files
   - Connects to backend API
   - Downloads IIF file
   - Imports into QuickBooks

3. **`python/test_iif_import.py`**
   - Standalone test script for IIF import
   - Tests importing a local IIF file

4. **`python/test_iif_auto_sync.py`**
   - Test script for full auto-sync workflow
   - Downloads from backend and imports

### Integration

- **`python/qb_sdk_service.py`** - Added `import_iif_file()` convenience method

## Quick Start

### Prerequisites

1. **Windows** (required - SDK is Windows-only)
2. **QuickBooks Desktop** running with company file open
3. **Python dependencies** installed:
   ```bash
   cd desktop-qbsdk/python
   pip install -r requirements.txt
   ```

### Test Local IIF Import

```bash
cd desktop-qbsdk/python
python test_iif_import.py
```

This will:
1. Ask for QuickBooks company file path
2. Ask for IIF file path
3. Connect to QuickBooks
4. Import the IIF file

### Test Auto-Sync from Backend

```bash
cd desktop-qbsdk/python
python test_iif_auto_sync.py
```

This will:
1. Ask for backend URL, API token, workspace ID
2. Ask for QuickBooks company file path
3. Optionally ask for file ID (or sync all files)
4. Download IIF file from backend
5. Import into QuickBooks automatically

## How It Works

### Method 1: SDK ImportData (Preferred)

Uses QuickBooks SDK's `ImportData` method:
```python
qb.ImportData(session_ticket, iif_file_path, 0)  # 0 = IIF format
```

**Pros:**
- Direct SDK method
- Fast and reliable
- No UI interaction needed

**Cons:**
- May not be available in all SDK versions
- Requires SDK to be properly installed

### Method 2: UI Automation (Fallback)

If SDK ImportData is not available, falls back to UI automation:
- Uses `pywinauto` to control QuickBooks window
- Navigates: File → Utilities → Import → IIF Files
- Selects and imports the file

**Pros:**
- Works when SDK ImportData is unavailable
- Works with any QuickBooks version

**Cons:**
- More fragile (breaks if UI changes)
- Requires QuickBooks window to be visible
- Slower than SDK method

## Integration with Electron App

The IIF import functionality can be integrated into the Electron app:

1. **Add IPC handler** in `electron/main.js`:
   ```javascript
   ipcMain.handle('import-iif', async (event, { filePath, companyFile }) => {
     // Call Python script to import IIF
   });
   ```

2. **Add UI button** in frontend:
   - "Auto-Import to QuickBooks" button
   - Calls IPC handler
   - Shows import status

3. **Use auto-sync service**:
   - Automatically download from backend
   - Import into QuickBooks
   - Show success/error message

## API Integration

The auto-sync service uses the existing backend endpoint:
```
GET /api/v1/export/quickbooks/queued/{workspace_id}?file_id={file_id}
```

This endpoint:
- Returns IIF file content
- Requires authentication (JWT token)
- Supports optional `file_id` parameter

## Error Handling

The import process handles:
- QuickBooks not running
- Company file not open
- SDK not available
- IIF file errors
- Network errors (for auto-sync)

## Next Steps

1. **Test the import functionality**:
   - Run `test_iif_import.py` with a sample IIF file
   - Verify it imports correctly

2. **Test auto-sync**:
   - Run `test_iif_auto_sync.py`
   - Verify it downloads and imports from backend

3. **Integrate into Electron app** (optional):
   - Add UI button for "Auto-Import"
   - Connect to backend API
   - Show import status

## Troubleshooting

### "ImportData method not available"
- The SDK version may not support ImportData
- Try UI automation fallback
- Or manually import via QuickBooks UI

### "Could not start QuickBooks"
- Ensure QuickBooks Desktop is running
- Ensure company file is open
- Check SDK installation

### "UI automation failed"
- Install `pywinauto`: `pip install pywinauto`
- Ensure QuickBooks window is visible
- Try SDK ImportData method instead

## Notes

- This is separate from the main desktop app (`desktop/` folder)
- Won't affect existing functionality
- Can be tested independently
- Can be integrated later if needed
