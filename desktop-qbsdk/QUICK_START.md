# Quick Start - Building Windows Installer

## Simple Build Command

From the `desktop-qbsdk` directory, run:

```bash
npm run build:win
```

The installer will be created in `dist/`.

### Bundling Python (Windows only, recommended)

To ship Python with the app so **users don't need to install Python**, run this **on a Windows machine** before `build:win`:

```bash
npm run build:python-embed
npm run build:win
```

See **EMBEDDED_PYTHON_BUILD.md** for details.

## Prerequisites

- Node.js 18+ installed
- Frontend built (or it will build automatically)

## First Time Build

On first build, electron-builder will:
1. Download Wine (for building Windows installers on macOS)
2. Download NSIS (Windows installer tool)
3. This may take 5-10 minutes

Subsequent builds are much faster.

## What Gets Created

After `npm run build:win`, you'll find:
- `dist/Sync Accounting Desktop SDK Setup 1.0.0.exe` - The Windows installer

## Testing

You can't test the .exe on macOS, but you can:
1. Transfer it to a Windows machine
2. Install and test it there
3. Or use a Windows VM

## Troubleshooting

**Wine installation issues:**
- If Wine installation fails, you can install it manually: `brew install wine-stable`
- Or use a Windows VM/CI for building

**Build fails:**
- Make sure frontend is built: `cd ../frontend && npm run build`
- Check Node.js version: `node --version` (should be 18+)


