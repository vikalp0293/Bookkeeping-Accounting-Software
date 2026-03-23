# Sync Accounting QB SDK – User Guide

> **Canonical location:** This guide is also maintained at [docs/user-guide](../../docs/user-guide/README.md) in the repo.

This guide walks you through everything you need to do to run the **Sync Accounting QB SDK** application on Windows. Follow the steps in order.

---

## Who This Is For

- **If you have the installer** (e.g. `Sync Accounting QB SDK Setup 1.0.0.exe`) → follow **Part A: Run the app**.
- **If you have the project source** and need to build the installer on Windows → follow **Part B: Build the installer**, then **Part A**.

---

## Part A: Run the Application

### Step 1: Install the app

1. Locate **Sync Accounting QB SDK Setup x.x.x.exe** (e.g. from `desktop-qbsdk\dist\` or from your team).
2. Double-click the installer.
3. Follow the wizard (install location, shortcuts). Finish the installation.
4. Launch **Sync Accounting QB SDK** from the Start Menu or desktop shortcut.

---

### Step 2: First launch – setup wizard

On **first launch**, the app runs an automatic setup check:

1. **Python**
   - If the app was built **with embedded Python** (recommended): Python is bundled or extracted automatically; you do **not** need to install Python.
   - If Python is missing: the app may offer to open the Python download page, or show instructions. Install Python 3.8+ from [python.org](https://www.python.org/) and check **“Add Python to PATH”**, then restart the app.

2. **Python dependencies**
   - If any are missing, the app will try to install them automatically (from bundled wheels or the internet).
   - If auto-install fails, you may see an option to **Install Dependencies** in the setup dialog, or you can install manually (see **PREREQUISITES_WINDOWS.md**).

3. **QuickBooks Desktop**
   - The app checks if QuickBooks Desktop is installed (or running).
   - If not installed: the app may offer to open the QuickBooks download page. Install QuickBooks Desktop Pro 2018 or later separately.

When all checks pass, you’ll see **“All requirements are met! You can start syncing.”** You can then continue to configuration.

---

### Step 3: Install and open QuickBooks (if not already)

1. Install **QuickBooks Desktop Pro** (2018 or newer) if you haven’t already.
2. Open **QuickBooks Desktop**.
3. Open your **company file** (`.QBW`) and leave QuickBooks open.  
   Sync requires QuickBooks to be **running with the company file open**.

---

### Step 4: Configure the app

In the Sync Accounting QB SDK app, open **Settings** (or the configuration screen) and set:

| Setting           | What to enter |
|-------------------|----------------|
| **Backend URL**   | Your API base URL (e.g. `https://dev-sync-api.kylientlabs.com`). |
| **API token**     | Your JWT token for the API. |
| **Workspace ID**  | The workspace you want to sync. |
| **Company file**  | Full path to your QuickBooks company file (e.g. `C:\Users\YourName\Documents\Company.qbw`). |

You can use **Browse** or **Select file** to pick the `.QBW` file instead of typing the path.

Optional: **Workspace account name** (if your backend uses it).

Save the settings.

---

### Step 5: Start sync

1. Ensure **QuickBooks Desktop is still open** with your company file loaded.
2. In the app, click **Start sync** (or the equivalent button).
3. The app will:
   - Use bundled or system Python.
   - Run the sync service and connect to QuickBooks via the SDK.
   - Sync data with your backend using the configured URL, token, and workspace.

If you see errors (e.g. “QuickBooks must be running”, “Company file not found”, “Python not found”), see **WINDOWS_TROUBLESHOOTING.md** and **HOW_TO_CHECK_LOGS.md**.

---

### Step 6: Stopping and re-running

- Click **Stop sync** in the app when you want to stop.
- To sync again: leave or reopen QuickBooks with the company file open, then click **Start sync** again.

---

## Part B: Build the Installer (Windows)

Use this only if you have the **project source** and want to build the Windows installer on a Windows PC.

### B.1 Install Node.js

1. Go to [https://nodejs.org](https://nodejs.org).
2. Download the **LTS** (e.g. 20.x) **64-bit** Windows installer.
3. Run it; accept defaults and ensure **“Add to PATH”** is checked.
4. Close and reopen Command Prompt or PowerShell.

### B.2 Get the project

- Clone or copy the **sync-software** repository onto the machine (e.g. `C:\Projects\sync-software`).

### B.3 Build embedded Python and the installer

Open **Command Prompt** or **PowerShell** and run:

```cmd
cd C:\Projects\sync-software\desktop-qbsdk
npm install
npm run build:python-embed
npm run build:win
```

- **`build:python-embed`** – Downloads and prepares Python so the installer can ship it; users won’t need to install Python separately.
- **`build:win`** – Builds the frontend and creates the Windows installer.

### B.4 Find and install the app

1. Open the folder: `desktop-qbsdk\dist\`.
2. You should see **Sync Accounting QB SDK Setup 1.0.0.exe** (or similar).
3. Run that `.exe` to install.
4. Then follow **Part A** from **Step 2** (first launch, QuickBooks, configure, start sync).

---

## Quick reference

| You have…                         | Do this… |
|-----------------------------------|----------|
| The .exe installer (with Python)  | **Part A**: Install app → First launch (setup wizard) → Open QuickBooks + company file → Configure (URL, token, workspace, company file) → Start sync. |
| The project source, no installer  | **Part B**: Install Node.js → `npm install` → `build:python-embed` → `build:win` → then **Part A**. |

---

## Requirements summary

- **Windows 10/11**, 64-bit.
- **QuickBooks Desktop** (2018+) installed and **running with company file open** when you sync.
- **Python**: Either shipped with the app (embedded build) or Python 3.8+ installed and in PATH (see **PREREQUISITES_WINDOWS.md**).
- **Configuration**: Backend URL, API token, workspace ID, and company file path set in the app.
- **Network**: Access to your backend API.

---

## Troubleshooting and logs

- **Troubleshooting (Python, QuickBooks, company file, etc.)**: **WINDOWS_TROUBLESHOOTING.md**
- **Log locations and how to read them**: **HOW_TO_CHECK_LOGS.md**
- **Prerequisites (Python, dependencies, manual install)**: **PREREQUISITES_WINDOWS.md**
