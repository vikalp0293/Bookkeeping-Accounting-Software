const { ipcMain, dialog } = require('electron');
const log = require('./logger').log;
const Store = require('electron-store');
const path = require('path');
const { app } = require('electron');

const store = new Store({
  name: 'settings',
  defaults: {
    backendUrl: 'https://dev-sync-api.kylientlabs.com',
    monitoredDirectory: '',
    autoStartMonitoring: false
  }
});

/**
 * Setup all IPC handlers
 */
function setupIpcHandlers() {
  // App info
  ipcMain.handle('app:get-version', () => {
    return app.getVersion();
  });

  // Settings
  ipcMain.handle('settings:get', () => {
    return store.store;
  });

  ipcMain.handle('settings:save', (event, settings) => {
    try {
      store.set(settings);
      log.info('Settings saved:', settings);
      return { success: true };
    } catch (error) {
      log.error('Failed to save settings:', error);
      return { success: false, error: error.message };
    }
  });

  // File operations
  ipcMain.handle('file:select-directory', async () => {
    const result = await dialog.showOpenDialog({
      properties: ['openDirectory'],
      title: 'Select Folder to Monitor'
    });

    if (!result.canceled && result.filePaths.length > 0) {
      return { success: true, path: result.filePaths[0] };
    }
    return { success: false };
  });

  ipcMain.handle('file:select-file', async () => {
    const result = await dialog.showOpenDialog({
      properties: ['openFile'],
      title: 'Select File',
      filters: [
        { name: 'PDF Files', extensions: ['pdf'] },
        { name: 'Image Files', extensions: ['jpg', 'jpeg', 'png', 'tiff', 'tif'] },
        { name: 'All Files', extensions: ['*'] }
      ]
    });

    if (!result.canceled && result.filePaths.length > 0) {
      return { success: true, path: result.filePaths[0] };
    }
    return { success: false };
  });

  // Logs
  ipcMain.handle('logs:get', async (event, logType) => {
    try {
      const fs = require('fs');
      const logPath = path.join(app.getPath('userData'), 'logs', `${logType || 'main'}.log`);
      
      if (fs.existsSync(logPath)) {
        const content = fs.readFileSync(logPath, 'utf-8');
        return { success: true, content };
      }
      return { success: true, content: 'No logs available' };
    } catch (error) {
      log.error('Failed to read logs:', error);
      return { success: false, error: error.message };
    }
  });

  // QWC file operations
  ipcMain.handle('qwc:get-path', () => {
    // Use the same logic as qbwc-setup.js
    const qbwcSetup = require('./qbwc-setup');
    const qwcPath = qbwcSetup.getQWCFilePath();
    
    if (qwcPath) {
      log.info(`QWC path requested: ${qwcPath}`);
      return { success: true, path: qwcPath };
    } else {
      log.error('QWC file not found when requested');
      return { success: false, error: 'QWC file not found' };
    }
  });

  ipcMain.handle('qwc:open-folder', async () => {
    const { shell } = require('electron');
    let resourcesPath;
    if (process.env.NODE_ENV === 'development') {
      resourcesPath = path.join(__dirname, '../resources');
    } else {
      // Try app.asar/resources first
      const asarResources = path.join(app.getAppPath(), 'resources');
      const fs = require('fs');
      if (fs.existsSync(asarResources)) {
        resourcesPath = asarResources;
      } else {
        // Fallback to process.resourcesPath (already points to resources folder)
        resourcesPath = process.resourcesPath;
      }
    }
    
    try {
      await shell.openPath(resourcesPath);
      return { success: true };
    } catch (error) {
      log.error('Failed to open QWC folder:', error);
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('qwc:open-file', async () => {
    const { shell } = require('electron');
    const qbwcSetup = require('./qbwc-setup');
    const qwcPath = qbwcSetup.getQWCFilePath();
    
    if (!qwcPath) {
      log.error('QWC file not found when trying to open');
      return { success: false, error: 'QWC file not found' };
    }
    
    try {
      log.info(`Opening QWC file: ${qwcPath}`);
      await shell.openPath(qwcPath);
      return { success: true };
    } catch (error) {
      log.error('Failed to open QWC file:', error);
      return { success: false, error: error.message };
    }
  });

  // QB Web Connector auto-setup
  const qbwcSetup = require('./qbwc-setup');
  
  ipcMain.handle('qwc:check-installed', async () => {
    try {
      const result = await qbwcSetup.checkQBWCInstalled();
      return result;
    } catch (error) {
      log.error('Failed to check QBWC installation:', error);
      return {
        installed: false,
        path: null,
        error: error.message
      };
    }
  });

  ipcMain.handle('qwc:auto-setup', async () => {
    try {
      const result = await qbwcSetup.autoSetupQBWC();
      log.info('QBWC auto-setup result:', result);
      return result;
    } catch (error) {
      log.error('QBWC auto-setup failed:', error);
      return {
        success: false,
        message: `Auto-setup failed: ${error.message}`,
        requiresUserAction: true,
        action: 'manual_setup'
      };
    }
  });

  ipcMain.handle('qwc:check-configured', async () => {
    try {
      const result = await qbwcSetup.checkQBWCConfigured();
      return result;
    } catch (error) {
      log.error('Failed to check QBWC configuration:', error);
      return {
        configured: false,
        message: `Check failed: ${error.message}`
      };
    }
  });

  // Reset QBWC setup flag (for testing/re-setup)
  ipcMain.handle('qwc:reset-setup-flag', () => {
    try {
      store.delete('qbwcSetupAttempted');
      log.info('QBWC setup flag reset - auto-setup will run on next launch');
      return { success: true };
    } catch (error) {
      log.error('Failed to reset QBWC setup flag:', error);
      return { success: false, error: error.message };
    }
  });

  // Directory monitoring
  const { getMonitor } = require('./directory-monitor');
  
  ipcMain.handle('monitor:start', async (event, directoryPath) => {
    try {
      const monitor = getMonitor();
      const settings = store.store;
      
      // Initialize monitor with current settings
      monitor.initialize({
        backendUrl: settings.backendUrl,
        authToken: settings.authToken,
        workspaceId: settings.workspaceId
      });
      
      const result = await monitor.startMonitoring(directoryPath);
      
      if (result.success) {
        // Save monitored directory to settings
        store.set('monitoredDirectory', directoryPath);
        log.info('Directory monitoring started:', directoryPath);
      }
      
      return result;
    } catch (error) {
      log.error('Failed to start monitoring:', error);
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('monitor:stop', async () => {
    try {
      const monitor = getMonitor();
      const result = await monitor.stopMonitoring();
      log.info('Directory monitoring stopped');
      return result;
    } catch (error) {
      log.error('Failed to stop monitoring:', error);
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('monitor:status', () => {
    try {
      const monitor = getMonitor();
      return { success: true, status: monitor.getStatus() };
    } catch (error) {
      log.error('Failed to get monitor status:', error);
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('monitor:initialize', (event, settings) => {
    try {
      const monitor = getMonitor();
      monitor.initialize(settings);
      
      // Save auth settings to store for later use
      if (settings.authToken) {
        store.set('authToken', settings.authToken);
      }
      if (settings.workspaceId) {
        store.set('workspaceId', settings.workspaceId);
      }
      if (settings.backendUrl) {
        store.set('backendUrl', settings.backendUrl);
      }
      
      log.info('Monitor initialized with settings');
      return { success: true };
    } catch (error) {
      log.error('Failed to initialize monitor:', error);
      return { success: false, error: error.message };
    }
  });

  log.info('IPC handlers registered');
}

module.exports = { setupIpcHandlers };

