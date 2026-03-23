# Prerequisites to Run Sync Accounting QB SDK on Windows

This document lists everything required to run the **desktop-qbsdk** (Sync Accounting QB SDK) app on a Windows machine.

---

## Embedded Python (no user install)

If the app was built **with embedded Python** (see **EMBEDDED_PYTHON_BUILD.md**), **users do not need to install Python**. The app ships with a bundled Python runtime and dependencies. Only the items below under **Operating System**, **QuickBooks Desktop**, **App configuration**, and **Network** apply.

If the app was built **without** embedded Python (e.g. built on macOS/Linux), users must install Python 3.8+ and dependencies as described in the rest of this document.

---

## 1. Operating System

| Requirement | Details |
|-------------|---------|
| **OS** | Windows 10 or Windows 11 |
| **Architecture** | 64-bit (x64) |

The QuickBooks SDK and the packaged app are built for 64-bit Windows only.

---

## 2. QuickBooks Desktop

| Requirement | Details |
|-------------|---------|
| **Product** | QuickBooks Desktop Pro (or compatible edition) |
| **Version** | 2018 or newer (e.g. 2018, 2019, 2020, etc.) |
| **State** | Must be **installed** and **running** when you use sync |
| **Company file** | Your QuickBooks company file (`.QBW`) must be **open** in QuickBooks |

**Important:**
- QuickBooks Desktop must be **open** with your company file loaded before starting sync.
- The app connects to QuickBooks via the SDK (COM); if QuickBooks is closed, sync will fail with “QuickBooks Desktop must be running.”

---

## 3. Python (only if app does *not* ship embedded Python)

| Requirement | Details |
|-------------|---------|
| **When needed** | Only when the installer was built **without** embedded Python (e.g. build on macOS). |
| **Version** | Python 3.8 or higher (3.9, 3.10, 3.11 recommended) |
| **Architecture** | 64-bit Python |
| **PATH** | Python must be added to the system PATH |

**Installation:**
1. Download from [python.org](https://www.python.org/downloads/).
2. Run the installer.
3. **Check “Add Python to PATH”** (critical).
4. Restart the computer (or at least restart the app) after installing.

**Verify:**
```cmd
python --version
```
Should show e.g. `Python 3.11.x`.

---

## 4. Python Dependencies (only if using system Python)

When the app uses **embedded Python**, dependencies are already included. When using **system Python**, the app uses these packages (installed automatically by the app from `requirements.txt`, or manually if needed):

| Package | Purpose |
|---------|---------|
| **pywin32** (≥306) | COM interface to QuickBooks SDK |
| **psutil** (≥5.9.0) | Check if QuickBooks process is running |
| **requests** (≥2.31.0) | HTTP calls to backend API |
| **pywinauto** (≥0.6.8) | UI automation (e.g. IIF import fallback) |

**Manual install (if app auto-install fails):**
```cmd
cd "%LOCALAPPDATA%\Programs\Sync Accounting QB SDK\resources\python"
python -m pip install -r requirements.txt
```
*(Path may differ; use the `python` folder next to the installed app.)*

---

## 5. App Configuration (after install)

Before sync can run, the app needs:

| Setting | Description |
|---------|-------------|
| **Backend URL** | API base URL (e.g. `https://dev-sync-api.kylientlabs.com`) |
| **API token** | JWT token for API authentication |
| **Workspace ID** | Workspace to sync |
| **Company file path** | Full path to your QuickBooks `.QBW` file (e.g. `C:\Users\...\Company.qbw`) |

Optional: **Workspace account name** (from workspace settings).

---

## 6. Network & Backend

| Requirement | Details |
|-------------|---------|
| **Internet** | Required for API calls and for installing Python dependencies |
| **Backend API** | Backend must be reachable at the configured URL |
| **Firewall** | Allow the app and `python.exe` to access the network if prompted |

---

## 7. Optional (for first-time setup)

- **QuickBooks Desktop SDK** – Usually installed with QuickBooks Desktop; the app uses the COM interface (`QBXMLRP2.RequestProcessor`) provided by QuickBooks.
- **Bundled Python installer** – Some installers bundle a Python installer; if not, the user is guided to install Python manually.

---

## Quick Checklist

Before running the app on a Windows machine, ensure:

- [ ] Windows 10/11, 64-bit  
- [ ] QuickBooks Desktop (2018+) installed  
- [ ] QuickBooks **open** with company file (`.QBW`) loaded  
- [ ] **Either** embedded Python is shipped with the app **or** Python 3.8+ is installed and in PATH  
- [ ] If using system Python: dependencies installed (`pywin32`, `psutil`, `requests`, `pywinauto`)  
- [ ] Backend URL, API token, workspace ID, and company file path configured in the app  
- [ ] Network access to the backend API  

---

## Troubleshooting

See **WINDOWS_TROUBLESHOOTING.md** for:

- Checking Python and QuickBooks processes  
- Log file locations (Electron + Python sync service)  
- Common errors (Python not found, QB not running, company file not found, etc.)  
- Diagnostic batch script  

See **HOW_TO_CHECK_LOGS.md** for log paths and how to read them.
