# Sync Accounting Desktop

Desktop application for automated bank statement and check processing with QuickBooks Desktop Pro 2018 integration.

## Development Setup

### Prerequisites

- Node.js 18+ installed
- npm or yarn package manager

### Installation

```bash
# Install dependencies
npm install

# Start development server (requires frontend dev server running)
npm run dev

# Build for production
npm run build:win
```

### Development Mode

1. Start the frontend dev server (in `frontend/` directory):
   ```bash
   cd ../frontend
   npm run dev
   ```

2. Start the Electron app:
   ```bash
   npm run dev
   ```

The Electron app will load from `http://localhost:5173` (or your Vite dev server URL).

### Project Structure

```
desktop/
├── electron/           # Electron main process files
│   ├── main.js        # Main entry point
│   ├── preload.js     # Preload script (security bridge)
│   ├── menu.js        # Application menu
│   └── logger.js      # Logging configuration
├── resources/         # App resources (icons, etc.)
├── package.json       # npm configuration
└── README.md          # This file
```

## Building

### Windows

```bash
npm run build:win
```

This will create an installer in the `dist/` directory.

## Notes

- The app requires the frontend to be built or running in dev mode
- In development, it connects to `http://localhost:5173`
- In production, it loads from `frontend/dist/index.html`

