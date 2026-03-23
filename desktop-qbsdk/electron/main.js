const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const log = require('electron-log');
const { spawn, execSync } = require('child_process');
const axios = require('axios');
const Store = require('electron-store');
const pythonChecker = require('./python-checker');
const { startLocalServer } = require('./local-server');
const setupWizard = require('./setup-wizard');
const { autoInstallPythonDependencies } = require('./auto-installer');
const pythonBundler = require('./python-bundler');
const AutoSyncManager = require('./auto-sync-manager');

// Configure logging - electron-log will use app name automatically
// But we set it explicitly to ensure unique path
log.transports.file.level = 'info';
log.transports.console.level = 'info';

// Initialize store with defaults
// Use unique name to avoid conflicts with main desktop app
const store = new Store({
  name: 'sync-accounting-qbsdk-settings',
  defaults: {
    backendUrl: 'https://dev-sync-api.kylientlabs.com',
    apiToken: '',
    workspaceId: null,
    companyFile: '',
    quickbooksDirectory: '',
    workspaceAccountName: '',
    monitoredDirectory: '',
    autoStartMonitoring: false
  }
});

let mainWindow = null;
let syncProcess = null;
let autoSyncManager = null;

// Export function to check if sync is running (for auto-sync-manager)
function isSyncRunning() {
  return syncProcess !== null && syncProcess.exitCode === null;
}

// Make it available for auto-sync-manager
module.exports.isSyncRunning = isSyncRunning;

function createWindow() {
  log.info('Creating main window...');

  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    title: 'QB Accounting SDK',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false,
      webSecurity: false,
    },
    icon: path.join(__dirname, '../resources/icons/icon.png'),
    show: true,
    titleBarStyle: 'default'
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.focus();
    log.info('Main window ready');
  });

  // Load the app
  if (process.env.NODE_ENV === 'development') {
    // In development, load from Vite dev server
    const devServerUrl = process.env.VITE_DEV_SERVER_URL || 'http://localhost:5173';
    log.info(`Loading from dev server: ${devServerUrl}`);
    mainWindow.loadURL(devServerUrl);
    mainWindow.webContents.openDevTools();
  } else {
    // In production, load from built files via local HTTP server
    // ES modules don't work with file:// protocol, so we serve via HTTP
    const appPath = app.getAppPath();
    log.info(`App path: ${appPath}`);
    
    // Try multiple possible paths (in order of likelihood)
    const possiblePaths = [
      path.join(appPath, 'frontend', 'dist'),  // Most likely in packaged app
      path.join(__dirname, '../frontend/dist'),    // Relative to electron/main.js
      path.join(process.resourcesPath, 'app.asar', 'frontend', 'dist'),  // Direct asar path
      path.join(__dirname, '../../frontend/dist') // Alternative relative path
    ];
    
    let frontendDistPath = null;
    for (const testPath of possiblePaths) {
      log.info(`Checking path: ${testPath}`);
      try {
        const indexPath = path.join(testPath, 'index.html');
        if (fs.existsSync(indexPath)) {
          frontendDistPath = testPath;
          log.info(`✓ Found frontend at: ${frontendDistPath}`);
          break;
        } else {
          log.warn(`✗ Path does not exist: ${testPath}`);
        }
      } catch (err) {
        log.warn(`✗ Error checking path ${testPath}: ${err.message}`);
      }
    }
    
    if (frontendDistPath) {
      // Start local HTTP server and load from it
      startLocalServer(frontendDistPath)
        .then((serverUrl) => {
          log.info(`Loading app from local server: ${serverUrl}`);
          mainWindow.loadURL(serverUrl).then(() => {
            log.info('Successfully loaded app from local server');
          }).catch((error) => {
            log.error(`Failed to load from local server: ${error.message}`);
            showErrorPage(mainWindow, `Failed to load application: ${error.message}\n\nCheck logs for details.`);
          });
        })
        .catch((error) => {
          log.error(`Failed to start local server: ${error.message}`);
          showErrorPage(mainWindow, `Failed to start local server: ${error.message}\n\nCheck logs for details.`);
        });
    } else {
      log.error('Frontend dist directory not found in any expected location');
      showErrorPage(mainWindow, 'Frontend files not found.\n\nPlease rebuild the application.');
    }
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  return mainWindow;
}

function showErrorPage(window, message) {
  const errorHTML = `
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <title>QB Accounting - Error</title>
      <style>
        body {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
          display: flex;
          justify-content: center;
          align-items: center;
          height: 100vh;
          margin: 0;
          background: #f5f5f5;
        }
        .error-container {
          background: white;
          padding: 40px;
          border-radius: 8px;
          box-shadow: 0 2px 10px rgba(0,0,0,0.1);
          max-width: 600px;
        }
        h1 {
          color: #d32f2f;
          margin-top: 0;
        }
        pre {
          background: #f5f5f5;
          padding: 15px;
          border-radius: 4px;
          overflow-x: auto;
          white-space: pre-wrap;
        }
      </style>
    </head>
    <body>
      <div class="error-container">
        <h1>Application Error</h1>
        <pre>${message}</pre>
        <p>Check the log file for more details.</p>
      </div>
    </body>
    </html>
  `;
  window.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(errorHTML)}`);
}

app.whenReady().then(async () => {
  // Run setup wizard on first launch (only on Windows)
  if (process.platform === 'win32') {
    try {
      // On first run, ensure bundled Python (zip) is extracted to userData before any checks.
      // This way the setup wizard and sync will see "Python installed" and use it.
      const hasConfigured = store.get('setupCompleted', false);
      if (!hasConfigured && app.isPackaged) {
        try {
          await pythonBundler.ensureBundledPythonReady();
        } catch (e) {
          log.warn('Bundled Python setup failed (will retry when syncing): ' + e.message);
        }
      }

      if (!hasConfigured) {
        log.info('First run detected, running setup wizard...');
        
        // Run auto-setup (checks everything and auto-installs what it can)
        const setupResult = await setupWizard.autoSetup();
        
        if (setupResult.success) {
          store.set('setupCompleted', true);
          log.info('Setup completed successfully');
        } else {
          // Show setup dialog with options for manual installation
          const dialogResult = await setupWizard.showSetupDialog(setupResult.results);
          if (dialogResult.canProceed) {
            store.set('setupCompleted', true);
          } else {
            // Store that we showed the dialog so we don't show it every time
            store.set('setupDialogShown', true);
          }
        }
      } else {
        // On subsequent launches, silently check and auto-install dependencies if needed
        try {
          const pythonCheck = await pythonChecker.checkPythonInstalled();
          if (pythonCheck) {
            const depsCheck = await pythonChecker.checkPythonDependencies();
            if (!depsCheck) {
              log.info('Python dependencies missing, auto-installing...');
              await autoInstallPythonDependencies();
            }
          }
        } catch (error) {
          log.warn(`Silent setup check failed: ${error.message}`);
          // Don't block app launch
        }
      }
    } catch (error) {
      log.error(`Setup wizard error: ${error.message}`);
      // Don't block app launch
    }
  }
  
  createWindow();

  // Initialize auto-sync manager
  autoSyncManager = new AutoSyncManager(
    async (config) => {
      // Callback to start sync when queued transactions are detected
      return await startSyncService(config);
    },
    () => {
      // Callback to check if sync is running
      return isSyncRunning();
    }
  );

  // Start auto-sync monitoring (will auto-start sync when transactions are queued)
  autoSyncManager.start();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    stopSyncService();
    if (autoSyncManager) {
      autoSyncManager.stop();
    }
    app.quit();
  }
});

app.on('before-quit', () => {
  stopSyncService();
  const { stopLocalServer } = require('./local-server');
  stopLocalServer();
});

// IPC Handlers
// App info
ipcMain.handle('app:get-version', () => {
  return app.getVersion();
});

// Settings (for frontend compatibility)
ipcMain.handle('settings:get', () => {
  return store.store;
});

ipcMain.handle('settings:save', (event, settings) => {
  try {
    // Merge with existing settings
    const currentSettings = store.store;
    const newSettings = { ...currentSettings, ...settings };
    store.set(newSettings);
    log.info('Settings saved:', newSettings);
    return { success: true };
  } catch (error) {
    log.error('Failed to save settings:', error);
    return { success: false, error: error.message };
  }
});

// Config (SDK-specific)
ipcMain.handle('get-config', () => {
  return {
    backendUrl: store.get('backendUrl', 'https://dev-sync-api.kylientlabs.com'),
    apiToken: store.get('apiToken', ''),
    workspaceId: store.get('workspaceId', null),
    companyFile: store.get('companyFile', ''),
    quickbooksDirectory: store.get('quickbooksDirectory', ''),
    workspaceAccountName: store.get('workspaceAccountName', ''),
    companyAccountMap: store.get('companyAccountMap', {}),
  };
});

ipcMain.handle('save-config', (event, config) => {
  store.set('backendUrl', config.backendUrl);
  store.set('apiToken', config.apiToken);
  store.set('workspaceId', config.workspaceId);
  store.set('companyFile', config.companyFile);
  store.set('quickbooksDirectory', config.quickbooksDirectory != null ? config.quickbooksDirectory : store.get('quickbooksDirectory', ''));
  store.set('workspaceAccountName', config.workspaceAccountName);
  if (config.companyAccountMap && typeof config.companyAccountMap === 'object') {
    store.set('companyAccountMap', config.companyAccountMap);
  }
  return { success: true };
});

// File operations (for frontend compatibility)
ipcMain.handle('file:select-directory', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openDirectory'],
    title: 'Select Folder'
  });

  if (!result.canceled && result.filePaths.length > 0) {
    return { success: true, path: result.filePaths[0] };
  }
  return { success: false };
});

ipcMain.handle('file:select-file', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openFile'],
    title: 'Select QuickBooks company file (.QBW)',
    filters: [
      { name: 'QuickBooks company file', extensions: ['qbw'] },
      { name: 'All Files', extensions: ['*'] }
    ]
  });

  if (!result.canceled && result.filePaths.length > 0) {
    return { success: true, path: result.filePaths[0] };
  }
  return { success: false };
});

// Select folder containing .QBW files (QuickBooks directory for multi-company)
ipcMain.handle('file:select-qb-directory', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openDirectory'],
    title: 'Select QuickBooks directory (folder containing .QBW files)'
  });
  if (!result.canceled && result.filePaths.length > 0) {
    return { success: true, path: result.filePaths[0] };
  }
  return { success: false };
});

// List .qbw files in a directory (for multi-company picker)
ipcMain.handle('qb:list-company-files', (event, dirPath) => {
  if (!dirPath || typeof dirPath !== 'string') {
    return { success: false, files: [], error: 'Invalid directory path' };
  }
  try {
    const resolved = path.resolve(dirPath.trim());
    if (!fs.existsSync(resolved) || !fs.statSync(resolved).isDirectory()) {
      return { success: false, files: [], error: 'Path is not a directory' };
    }
    const entries = fs.readdirSync(resolved, { withFileTypes: true });
    const files = entries
      .filter(e => e.isFile() && e.name.toLowerCase().endsWith('.qbw'))
      .map(e => {
        const fullPath = path.join(resolved, e.name);
        return { path: fullPath, name: e.name };
      })
      .sort((a, b) => a.name.localeCompare(b.name));
    return { success: true, files };
  } catch (err) {
    log.warn('qb:list-company-files failed:', err.message);
    return { success: false, files: [], error: err.message };
  }
});

// Logs (for frontend compatibility)
ipcMain.handle('logs:get', async (event, logType) => {
  try {
    const fs = require('fs');
    // Use unique log directory to avoid conflicts
    const logDir = path.join(app.getPath('userData'), 'logs');
    const logPath = path.join(logDir, `${logType || 'main'}.log`);
    
    // Ensure log directory exists
    if (!fs.existsSync(logDir)) {
      fs.mkdirSync(logDir, { recursive: true });
    }
    
    if (fs.existsSync(logPath)) {
      const content = fs.readFileSync(logPath, 'utf-8');
      // Return last 1000 lines to avoid huge files
      const lines = content.split('\n');
      const lastLines = lines.slice(-1000).join('\n');
      return { success: true, content: lastLines, fullPath: logPath };
    }
    return { success: true, content: 'No logs available', fullPath: logPath };
  } catch (error) {
    log.error('Failed to read logs:', error);
    return { success: false, error: error.message };
  }
});

// Get log directory path
ipcMain.handle('logs:get-path', () => {
  const logDir = path.join(app.getPath('userData'), 'logs');
  return { success: true, path: logDir };
});

// Open log directory in file explorer
ipcMain.handle('logs:open-directory', () => {
  const logDir = path.join(app.getPath('userData'), 'logs');
  const { shell } = require('electron');
  shell.openPath(logDir);
  return { success: true, path: logDir };
});

// Make start-sync available as a function for auto-sync manager
async function startSyncService(config) {
  if (syncProcess) {
    return { success: false, error: 'Sync service already running' };
  }

  // Validate Windows platform
  if (process.platform !== 'win32') {
    return { success: false, error: 'QuickBooks SDK only works on Windows' };
  }

  // Validate required config
  if (!config.apiToken || !config.workspaceId || !config.companyFile) {
    return { success: false, error: 'Missing required configuration (API token, workspace ID, or company file)' };
  }

  // On Windows: if installer had zip only (Mac build), extract to userData on first run
  await pythonBundler.ensureBundledPythonReady();

  // Use bundled Python when available; otherwise require system Python (or offer installer)
  const pythonInstalled = await pythonChecker.checkPythonInstalled();
  if (!pythonInstalled) {
    if (pythonBundler.hasBundledPython()) {
      log.warn('Bundled Python folder exists but python.exe failed to run');
      return { success: false, error: 'Bundled Python could not be started. Try reinstalling the app.' };
    }
    log.info('Python not found, attempting auto-install...');
    try {
      const bundledInstaller = pythonBundler.getBundledPythonInstaller();
      if (bundledInstaller) {
        const result = await pythonBundler.runBundledPythonInstaller();
        if (result.success) {
          return {
            success: false,
            error: 'Python installer is running. Please complete the installation and restart the app, then try again.'
          };
        }
      }
      await pythonBundler.autoInstallPython();
      await new Promise(resolve => setTimeout(resolve, 2000));
    } catch (error) {
      log.error(`Auto-install Python failed: ${error.message}`);
      return {
        success: false,
        error: `Python is not installed. Please install Python 3.8+ from https://www.python.org/ and make sure to check "Add Python to PATH" during installation.`
      };
    }
  }

  // Verify Python environment before starting
  try {
    await pythonChecker.verifyPythonEnvironment();
  } catch (error) {
    // Try auto-installing dependencies
    log.info('Python dependencies missing, attempting auto-install...');
    try {
      await autoInstallPythonDependencies();
      // Re-check
      const depsInstalled = await pythonChecker.checkPythonDependencies();
      if (!depsInstalled) {
        return { success: false, error: error.message };
      }
    } catch (installError) {
      return { success: false, error: error.message };
    }
  }

  try {
    // Save config
    store.set('backendUrl', config.backendUrl);
    store.set('apiToken', config.apiToken);
    store.set('workspaceId', config.workspaceId);
    store.set('companyFile', config.companyFile);
    store.set('workspaceAccountName', config.workspaceAccountName);

    // Resolve QuickBooks account for this company: per-company override > backend workspace > config
    const companyAccountMap = store.get('companyAccountMap', {}) || {};
    let workspaceAccountNameForSync = (companyAccountMap[config.companyFile] && companyAccountMap[config.companyFile].trim())
      ? companyAccountMap[config.companyFile].trim()
      : (config.workspaceAccountName || '');
    if (!workspaceAccountNameForSync) {
      try {
        const token = config.access_token || config.apiToken;
        const workspacesUrl = `${config.backendUrl.replace(/\/$/, '')}/api/v1/workspaces`;
        const res = await axios.get(workspacesUrl, {
          headers: { Authorization: `Bearer ${token}` },
          timeout: 10000
        });
        const workspaces = Array.isArray(res.data) ? res.data : [];
        const workspace = workspaces.find(w => Number(w.id) === Number(config.workspaceId));
        if (workspace && workspace.quickbooks_account_name) {
          workspaceAccountNameForSync = workspace.quickbooks_account_name;
          log.info(`Using workspace account name from backend: ${workspaceAccountNameForSync}`);
        }
      } catch (fetchErr) {
        const msg = fetchErr.response ? `${fetchErr.response.status} ${fetchErr.response.statusText}` : fetchErr.message;
        log.warn(`Could not fetch workspace account from backend: ${msg}; using local setting`);
      }
    } else {
      log.info(`Using account for this company: ${workspaceAccountNameForSync}`);
    }

    // Start Python sync service
    const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
    let pythonScript, pythonExe;
    
    if (isDev) {
      pythonScript = path.join(__dirname, '../python/sync_runner.py');
      pythonExe = process.platform === 'win32' ? 'python' : 'python3';
    } else {
      pythonScript = path.join(process.resourcesPath, 'python', 'sync_runner.py');
      pythonExe = pythonBundler.getPythonPath();
    }

    log.info(`Starting sync service: ${pythonExe} ${pythonScript}`);
    log.info(`Working directory: ${isDev ? path.join(__dirname, '..') : process.resourcesPath}`);
    log.info(`Backend URL: ${config.backendUrl}`);
    log.info(`Workspace ID: ${config.workspaceId}`);
    log.info(`Company File: ${config.companyFile}`);
    
    // Verify Python script exists
    if (!fs.existsSync(pythonScript)) {
      const error = `Python script not found: ${pythonScript}`;
      log.error(error);
      if (mainWindow) {
        mainWindow.webContents.send('sync-error', error);
      }
      return { success: false, error };
    }

    // Verify Python executable exists (if it's a full path)
    if (pythonExe.includes(path.sep) && !fs.existsSync(pythonExe)) {
      const error = `Python executable not found: ${pythonExe}`;
      log.error(error);
      if (mainWindow) {
        mainWindow.webContents.send('sync-error', error);
      }
      return { success: false, error };
    }

    log.info(`Python executable: ${pythonExe}, Script: ${pythonScript}, CWD: ${isDev ? path.join(__dirname, '..') : process.resourcesPath}`);
    
    // Test Python before spawning
    log.info('Testing Python executable...');
    try {
      const testResult = execSync(`"${pythonExe}" --version`, { 
        encoding: 'utf-8',
        timeout: 5000,
        shell: true 
      });
      log.info(`Python version check: ${testResult.trim()}`);
    } catch (testError) {
      const error = `Python test failed: ${testError.message}. Python may not be installed or not in PATH.`;
      log.error(error);
      if (mainWindow) {
        mainWindow.webContents.send('sync-error', error);
      }
      return { success: false, error };
    }

    const spawnCwd = isDev ? path.join(__dirname, '..') : process.resourcesPath;
    const userDataLogDir = path.join(app.getPath('userData'), 'logs');
    const spawnEnv = {
      ...process.env,
      BACKEND_URL: config.backendUrl,
      API_TOKEN: config.apiToken,
      WORKSPACE_ID: config.workspaceId.toString(),
      COMPANY_FILE: config.companyFile,
      WORKSPACE_ACCOUNT_NAME: workspaceAccountNameForSync || '',
      LOG_DIR: userDataLogDir, // writable; Program Files is not
    };
    // Ensure app Python scripts are importable (our python/ folder)
    const pythonDir = isDev ? path.join(__dirname, '../python') : path.join(process.resourcesPath, 'python');
    spawnEnv.PYTHONPATH = spawnEnv.PYTHONPATH ? `${pythonDir}${path.delimiter}${spawnEnv.PYTHONPATH}` : pythonDir;

    // Use shell: false so paths with spaces (e.g. C:\Program Files\Sync Accounting QB SDK\...) are passed as single arguments
    syncProcess = spawn(pythonExe, [pythonScript], {
      cwd: spawnCwd,
      env: spawnEnv,
      shell: false
    });

    syncProcess.stdout.on('data', (data) => {
      const output = data.toString();
      log.info(`Sync service stdout: ${output}`);
      if (mainWindow) {
        mainWindow.webContents.send('sync-log', output);
      }
    });

    syncProcess.stderr.on('data', (data) => {
      const output = data.toString();
      log.error(`Sync service stderr: ${output}`);
      if (mainWindow) {
        mainWindow.webContents.send('sync-error', output);
      }
    });

    syncProcess.on('error', (error) => {
      const logPath = path.join(app.getPath('userData'), 'logs', 'main.log');
      const errorMsg = `❌ FAILED TO START PYTHON SYNC SERVICE\n\nError: ${error.message}\n\nPossible causes:\n1. Python is not installed\n2. Python is not in PATH\n3. Python executable not found: ${pythonExe}\n\nTo fix:\n1. Install Python 3.8+ from https://www.python.org/\n2. During installation, check "Add Python to PATH"\n3. Restart your computer\n4. Verify: Open Command Prompt and type "python --version"\n\nLog file: ${logPath}`;
      log.error(`Sync process spawn error: ${error.message}`, error);
      log.error(`Python executable: ${pythonExe}`);
      log.error(`Python script: ${pythonScript}`);
      log.error(`Working directory: ${isDev ? path.join(__dirname, '..') : process.resourcesPath}`);
      log.error(`Error code: ${error.code}`);
      log.error(`Error syscall: ${error.syscall}`);
      syncProcess = null;
      if (mainWindow) {
        mainWindow.webContents.send('sync-error', errorMsg);
        // Also show a dialog for critical errors
        dialog.showErrorBox(
          'Sync Service Failed to Start',
          errorMsg
        );
      }
    });

    syncProcess.on('close', (code) => {
      log.info(`Sync service exited with code ${code}`);
      syncProcess = null;
      if (mainWindow) {
        mainWindow.webContents.send('sync-stopped', code);
      }
    });

    // Wait a moment to see if process starts successfully
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    // Check if process is still alive
    if (syncProcess && syncProcess.killed) {
      const error = 'Python process exited immediately after starting. Check logs for details.';
      log.error(error);
      syncProcess = null;
      if (mainWindow) {
        mainWindow.webContents.send('sync-error', error);
      }
      return { success: false, error };
    }
    
    log.info('Python sync service process started successfully');
    return { success: true };
  } catch (error) {
    const errorMsg = `Failed to start sync service: ${error.message}\n\nCheck logs: ${path.join(app.getPath('userData'), 'logs', 'main.log')}`;
    log.error(`Failed to start sync service: ${error.message}`, error);
    if (mainWindow) {
      mainWindow.webContents.send('sync-error', errorMsg);
    }
    return { success: false, error: error.message };
  }
}

ipcMain.handle('start-sync', async (event, config) => {
  // Resolve workspace from API so we use the current user's workspace (avoids 403 when store has stale workspaceId)
  const token = config?.access_token || config?.apiToken;
  if (token && config?.backendUrl) {
    try {
      const defaultUrl = `${(config.backendUrl || '').replace(/\/$/, '')}/api/v1/workspaces/default`;
      const res = await axios.get(defaultUrl, { headers: { Authorization: `Bearer ${token}` }, timeout: 8000 });
      if (res.data && res.data.id != null) {
        config.workspaceId = res.data.id;
        store.set('workspaceId', config.workspaceId);
      }
    } catch (err) {
      log.warn('Could not resolve workspace from API:', err.response ? `${err.response.status}` : err.message);
    }
  }
  return await startSyncService(config);
});

ipcMain.handle('stop-sync', () => {
  if (syncProcess) {
    log.info('Stopping sync service...');
    syncProcess.kill();
    syncProcess = null;
    return { success: true };
  }
  return { success: false, error: 'Sync service not running' };
});

ipcMain.handle('get-sync-status', () => {
  return {
    running: syncProcess !== null,
  };
});

// Trigger immediate sync check (called after transactions are queued)
ipcMain.handle('trigger-sync-check', async () => {
  log.info('trigger-sync-check invoked from frontend');
  if (autoSyncManager) {
    await autoSyncManager.triggerImmediateCheck();
    return { success: true };
  }
  log.warn('trigger-sync-check: autoSyncManager not initialized');
  return { success: false, error: 'Auto-sync manager not initialized' };
});

ipcMain.handle('check-python', async () => {
  try {
    const pythonInstalled = await pythonChecker.checkPythonInstalled();
    const depsInstalled = await pythonChecker.checkPythonDependencies();
    
    return {
      success: true,
      pythonInstalled,
      depsInstalled,
      ready: pythonInstalled && depsInstalled
    };
  } catch (error) {
    return {
      success: false,
      error: error.message
    };
  }
});

ipcMain.handle('install-python-deps', async () => {
  try {
    await pythonChecker.installPythonDependencies();
    return { success: true };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

// Setup wizard handlers
ipcMain.handle('setup:check', async () => {
  try {
    const results = await setupWizard.runSetupCheck();
    return { success: true, results };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

ipcMain.handle('setup:auto', async () => {
  try {
    const result = await setupWizard.autoSetup();
    return result;
  } catch (error) {
    return { success: false, error: error.message };
  }
});

ipcMain.handle('setup:dialog', async (event, results) => {
  try {
    const result = await setupWizard.showSetupDialog(results);
    return result;
  } catch (error) {
    return { canProceed: false, error: error.message };
  }
});

function stopSyncService() {
  if (syncProcess) {
    log.info('Stopping sync service on app quit...');
    syncProcess.kill();
    syncProcess = null;
  }
}

