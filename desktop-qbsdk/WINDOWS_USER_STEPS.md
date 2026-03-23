# Steps on a Windows Machine (QuickBooks Only)

**For the full step-by-step process to run the application, see [USER_GUIDE.md](USER_GUIDE.md).**

This page is a short summary.

---

## If you have the installer (.exe)

1. **Install** – Double-click **Sync Accounting QB SDK Setup x.x.x.exe** and complete the wizard.
2. **First launch** – Open the app; the setup wizard checks Python, dependencies, and QuickBooks. Fix any missing items (Python/deps may auto-install).
3. **QuickBooks** – Open QuickBooks Desktop and open your company file (`.QBW`). Leave it open.
4. **Configure** – In the app, set Backend URL, API token, Workspace ID, and company file path (e.g. via **Browse** for the `.QBW` file).
5. **Start sync** – Click **Start sync** in the app.

---

## If you need to build the installer on Windows

1. Install **Node.js** (LTS, 64-bit) from [nodejs.org](https://nodejs.org); ensure “Add to PATH” is checked.
2. Clone/copy the **sync-software** repo (e.g. `C:\Projects\sync-software`).
3. In a terminal:
   ```cmd
   cd C:\Projects\sync-software\desktop-qbsdk
   npm install
   npm run build:python-embed
   npm run build:win
   ```
4. Run the installer from `desktop-qbsdk\dist\Sync Accounting QB SDK Setup 1.0.0.exe`, then follow the steps above (first launch → QuickBooks → configure → start sync).

---

## Required in all cases

- **QuickBooks Desktop** installed and **running** with your **company file open** when you sync.
- **Backend URL**, **API token**, **Workspace ID**, and **company file path** set in the app.
- **Network** access to your backend API.

If the installer was **not** built with embedded Python (e.g. built on macOS), you may need to install **Python 3.8+** and add it to PATH; see **PREREQUISITES_WINDOWS.md**.

**Full details:** [USER_GUIDE.md](USER_GUIDE.md)  
**Troubleshooting:** [WINDOWS_TROUBLESHOOTING.md](WINDOWS_TROUBLESHOOTING.md)  
**Logs:** [HOW_TO_CHECK_LOGS.md](HOW_TO_CHECK_LOGS.md)
