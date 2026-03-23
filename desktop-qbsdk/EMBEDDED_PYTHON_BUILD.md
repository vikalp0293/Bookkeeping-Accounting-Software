# Building the App with Embedded Python (Option B)

This document describes how to build the **desktop-qbsdk** app so it **ships Python** with the installer. Users then do **not** need to install Python on Windows.

---

## Overview

- **Embedded Python** = Python Windows embeddable package (e.g. 3.10.11) + pip + app dependencies (pywin32, psutil, requests, pywinauto), all placed in `resources/python-portable/`.
- The Electron build packs this folder as **extraResources** so the installed app has `python-portable/python.exe` and can run the sync service without a system Python install.

---

## When to build with embedded Python

- **On Windows:** You can run the embedded Python build step so the installer includes Python.
- **On macOS/Linux:** You cannot run the embed step (it uses Windows embed + pip on Windows). The Windows installer built from macOS will still work, but users will need to install Python 3.8+ themselves (or use the optional bundled Python installer).

---

## Steps (on Windows)

### 1. Build embedded Python

From the `desktop-qbsdk` directory on a **Windows** machine:

```bash
npm run build:python-embed
```

This script:

1. Downloads the Python 3.10.11 Windows embeddable package (zip).
2. Extracts it to `resources/python-portable/`.
3. Enables `import site` in the embed’s `._pth` file so `site-packages` is used.
4. Runs `get-pip.py` to install pip.
5. Runs `pip install -r python/requirements.txt` so pywin32, psutil, requests, pywinauto are installed.

After it finishes, `resources/python-portable/` contains a full Python runtime and dependencies.

### 2. Build the Windows installer

```bash
npm run build:win
```

This will:

- Build the frontend and copy it.
- Run `prepare:python` (and optionally `build:python-embed` again; you can skip if you already ran it).
- Run `bundle:deps` if applicable.
- Run electron-builder; **extraResources** will copy `resources/python-portable/` into the built app.

The installer will be at `dist/Sync Accounting QB SDK Setup 1.0.0.exe` (or similar).

### 3. Verify

Install the built app on a Windows machine that does **not** have Python installed. Configure backend, workspace, and company file, then start sync. The app should use `python-portable/python.exe` and run without asking the user to install Python.

---

## Build from macOS/Linux (no embedded Python)

If you run only:

```bash
npm run build:win
```

from macOS or Linux, `build:python-embed` is skipped (the script exits early on non-Windows). The `resources/python-portable/` folder will only contain the placeholder README. The resulting installer will **not** include Python; users must install Python 3.8+ and dependencies as described in **PREREQUISITES_WINDOWS.md**.

---

## Troubleshooting

- **“Python embed zip download failed”**  
  Check network and the Python FTP URL in `scripts/build-embedded-python.js` (e.g. `https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-amd64.zip`).

- **“get-pip.py failed” or “pip install failed”**  
  Ensure the build machine has internet. If the embed’s `._pth` was not updated, `import site` may be disabled; the script uncomments it. Re-run `npm run build:python-embed`.

- **App says “Python is not available” even after building with embed**  
  Confirm `resources/python-portable/python.exe` exists after the embed step and that **extraResources** in `package.json` includes `resources/python-portable` → `python-portable`. Check the installed app’s resources folder (e.g. next to the exe) for `python-portable/python.exe`.

- **Sync fails with “No module named win32com”**  
  Dependencies were not installed into the embed. On Windows, run `npm run build:python-embed` again and ensure it completes without errors, then rebuild the installer.

---

## Summary

| Build environment | Run `build:python-embed`? | Installer includes Python? |
|-------------------|----------------------------|----------------------------|
| Windows           | Yes                        | Yes                        |
| macOS / Linux     | No (script skips)           | No                         |

To give users a **no-Python-install** experience, build the Windows installer on a Windows machine and run `npm run build:python-embed` before `npm run build:win`.
