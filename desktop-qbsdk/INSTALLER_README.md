# Sync Accounting QB SDK - Installer Guide

## Overview

This installer creates a **separate** application from the main "Sync Accounting Desktop" app. Both can run simultaneously on the same Windows machine without conflicts.

## Key Differences from Main Desktop App

| Feature | Main Desktop App | QB SDK App |
|---------|-----------------|------------|
| **App ID** | `com.syncaccounting.desktop` | `com.syncaccounting.qbsdk` |
| **Product Name** | "Sync Accounting Desktop" | "Sync Accounting QB SDK" |
| **Shortcut Name** | "Sync Accounting Desktop" | "Sync Accounting QB SDK" |
| **Settings Store** | `sync-accounting-desktop-settings` | `sync-accounting-qbsdk-settings` |
| **Installation Path** | `C:\Program Files\Sync Accounting Desktop` | `C:\Program Files\Sync Accounting QB SDK` |
| **Purpose** | Folder monitoring, extraction, QB Web Connector | IIF auto-import via SDK |

## Building the Installer

### Prerequisites

1. **Node.js 18+** installed
2. **Frontend built** (or it will build automatically)
3. **Python installer** (optional - for bundling with installer)

### Build Command

```bash
cd desktop-qbsdk
npm run build:win
```

This will:
1. Build the frontend (`npm run build:frontend`)
2. Copy frontend to desktop app (`npm run copy:frontend`)
3. Prepare Python files (`npm run prepare:python`)
4. Create Windows installer (`electron-builder --win --x64`)

### Output

The installer will be created at:
```
desktop-qbsdk/dist/Sync Accounting QB SDK Setup 1.0.0.exe
```

## Python Installation

### Automatic Installation (During Installer)

The installer will:
1. **Check for Python** (3.8, 3.9, 3.10, or 3.11)
2. **If not found**, offer to install Python 3.11.9:
   - If Python installer is bundled → Installs automatically
   - If not bundled → Opens python.org download page
3. **User can skip** and install manually later

### Bundling Python Installer (Optional)

To bundle Python installer with the app:

1. Download Python 3.11.9 (64-bit) from:
   https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe

2. Place it in:
   ```
   desktop-qbsdk/resources/python-installer/python-3.11.9-amd64.exe
   ```

3. The installer will automatically use it if Python is not found

### Manual Python Installation

If user installs Python manually:
- Must be Python 3.8 or higher
- **CRITICAL**: Check "Add Python to PATH" during installation
- Restart computer after installation

## First Launch Behavior

On first launch, the app will:

1. **Check for Python**:
   - If not found → Shows setup wizard with Python installation instructions
   - If found → Continues to next check

2. **Check Python Dependencies**:
   - If missing → Automatically installs from `requirements.txt`
   - Uses: `pip install -r requirements.txt`

3. **Check QuickBooks Desktop**:
   - Verifies QuickBooks is installed
   - Prompts user to open company file if needed

## Installation Requirements

### User's System Must Have:

1. **Windows 10/11** (64-bit)
2. **Python 3.8+** (installed automatically or manually)
3. **QuickBooks Desktop Pro 2018+** (user must install separately)
4. **Internet connection** (for downloading Python dependencies)

## No Conflicts with Main Desktop App

Both apps can run simultaneously because:

✅ **Different App IDs** - Different registry entries  
✅ **Different Settings Stores** - Separate configuration files  
✅ **Different Installation Paths** - Separate program folders  
✅ **Different Shortcut Names** - Different Start Menu entries  
✅ **Different Ports** - Different local server ports (if both running)

## Testing the Installer

### On Windows Machine:

1. **Build the installer** (from macOS/Linux):
   ```bash
   cd desktop-qbsdk
   npm run build:win
   ```

2. **Transfer to Windows**:
   - Copy `dist/Sync Accounting QB SDK Setup 1.0.0.exe` to Windows machine

3. **Run installer**:
   - Double-click the installer
   - Follow installation wizard
   - Python installation will be offered if needed

4. **Launch app**:
   - App will check for Python and dependencies
   - Setup wizard will guide through configuration

## Troubleshooting

### Python Not Detected After Installation

- **Solution**: Restart computer (required for PATH changes)
- **Alternative**: Manually add Python to PATH in System Environment Variables

### Python Dependencies Fail to Install

- **Check**: Internet connection
- **Check**: Python is in PATH: `python --version`
- **Manual**: Run `pip install -r requirements.txt` in `python/` folder

### Installer Build Fails

- **Check**: Frontend is built: `cd ../frontend && npm run build`
- **Check**: Node.js version: `node --version` (should be 18+)
- **Check**: All dependencies installed: `npm install`

## File Structure

```
desktop-qbsdk/
├── build/
│   └── installer.nsh          # NSIS installer script (Python check)
├── python/
│   ├── iif_importer.py         # IIF import functionality
│   ├── iif_auto_sync.py        # Auto-sync service
│   ├── install_dependencies.bat # Dependency installer
│   └── requirements.txt        # Python dependencies
├── resources/
│   └── python-installer/
│       └── python-3.11.9-amd64.exe  # Python installer (optional)
└── dist/
    └── Sync Accounting QB SDK Setup 1.0.0.exe  # Final installer
```

## Next Steps After Installation

For the complete step-by-step process for end users, see **[USER_GUIDE.md](USER_GUIDE.md)**.

Summary:
1. **Launch the app** – It will run the setup wizard (Python, dependencies, QuickBooks checks).
2. **Configure** – Backend URL, API token, workspace ID, company file path (e.g. via Browse for .QBW).
3. **Open QuickBooks** – Open your company file and leave QuickBooks running.
4. **Start sync** – Click Start sync in the app.
