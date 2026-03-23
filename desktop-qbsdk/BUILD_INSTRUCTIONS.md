# Building Sync Accounting QB SDK Installer

## Quick Build

```bash
cd desktop-qbsdk
npm run build:win
```

The installer will be created in `dist/Sync Accounting QB SDK Setup 1.0.0.exe`

## Prerequisites

1. **Node.js 18+** installed
2. **Frontend built** (or it will build automatically)
3. **Python installer** (optional - for bundling)

## Step-by-Step Build Process

### 1. Install Dependencies

```bash
cd desktop-qbsdk
npm install
```

### 2. Build Frontend (if not already built)

```bash
cd ../frontend
npm run build
cd ../desktop-qbsdk
```

### 3. Build Installer

```bash
npm run build:win
```

This command:
- Builds frontend (if needed)
- Copies frontend to `desktop-qbsdk/frontend/dist`
- Prepares Python files
- Creates Windows installer using electron-builder

### 4. Find Installer

The installer will be at:
```
desktop-qbsdk/dist/Sync Accounting QB SDK Setup 1.0.0.exe
```

## Bundling Python Installer (Optional)

To automatically install Python during setup:

1. Download Python 3.11.9 (64-bit):
   https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe

2. Place it in:
   ```
   desktop-qbsdk/resources/python-installer/python-3.11.9-amd64.exe
   ```

3. Rebuild installer:
   ```bash
   npm run build:win
   ```

## Installer Features

✅ **Separate from main desktop app** - Different app ID, name, and paths  
✅ **Python auto-detection** - Checks for Python 3.8+ during installation  
✅ **Python auto-install** - Offers to install Python if not found  
✅ **Dependency auto-install** - Installs Python packages on first launch  
✅ **No conflicts** - Can run alongside main desktop app  

## Testing

1. Transfer installer to Windows machine
2. Run installer
3. Verify Python installation prompt (if Python not installed)
4. Launch app and verify setup wizard works
5. Test IIF import functionality

## Troubleshooting

**Build fails:**
- Ensure frontend is built: `cd ../frontend && npm run build`
- Check Node.js version: `node --version` (should be 18+)
- Run `npm install` to ensure all dependencies are installed

**Python installer not found:**
- This is optional - installer will prompt user to download Python manually
- To bundle Python, download and place in `resources/python-installer/`

**Installer conflicts with main app:**
- Both apps use different:
  - App IDs (`com.syncaccounting.desktop` vs `com.syncaccounting.qbsdk`)
  - Product names
  - Installation paths
  - Settings stores
- They can run simultaneously without conflicts
