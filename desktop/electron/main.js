const { app, BrowserWindow, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const log = require('electron-log');
const { setupMenu } = require('./menu');
const { setupLogger } = require('./logger');
const { setupIpcHandlers } = require('./ipc-handlers');
const { startLocalServer, stopLocalServer } = require('./local-server');
const Store = require('electron-store');

// Configure logging
setupLogger();

let mainWindow = null;

/**
 * Check and auto-setup QuickBooks Web Connector on first launch
 */
async function checkAndSetupQBWC(window) {
  if (process.platform !== 'win32') {
    log.info('QBWC auto-setup skipped: Not on Windows');
    return; // Only on Windows
  }

  const store = new Store({ name: 'settings' });
  const qbwcSetupAttempted = store.get('qbwcSetupAttempted', false);
  
  // Skip if already attempted
  if (qbwcSetupAttempted) {
    log.info('QBWC setup already attempted, skipping auto-setup');
    log.info('To reset: Delete the settings file or manually trigger setup from Settings page');
    return;
  }

  log.info('QBWC auto-setup: Starting first-time setup check...');

  try {
    const qbwcSetup = require('./qbwc-setup');
    
    // First, check if QWC file exists
    const qwcPath = qbwcSetup.getQWCFilePath();
    if (!qwcPath) {
      log.warn('QBWC auto-setup: QWC file not found!');
      log.warn('This is likely why auto-setup is not working.');
      log.warn('Expected location: process.resourcesPath/sync_accounting.qwc');
      log.warn(`process.resourcesPath: ${process.resourcesPath}`);
      store.set('qbwcSetupAttempted', true);
      
      // Show error dialog to user
      dialog.showMessageBox(window, {
        type: 'warning',
        title: 'QuickBooks Web Connector Setup',
        message: 'Configuration File Not Found',
        detail: 'The QuickBooks Web Connector configuration file (.qwc) was not found.\n\nPlease reinstall the application or contact support.',
        buttons: ['OK'],
        defaultId: 0
      }).catch(err => {
        log.error('Error showing QWC file missing dialog:', err);
      });
      return;
    }
    
    log.info(`QBWC auto-setup: QWC file found at: ${qwcPath}`);
    
    // Check if QBWC is installed
    const checkResult = await qbwcSetup.checkQBWCInstalled();
    
    if (!checkResult.installed) {
      log.info('QB Web Connector not installed, skipping auto-setup');
      store.set('qbwcSetupAttempted', true);
      return;
    }

    log.info('QBWC is installed, attempting auto-setup...');
    // Attempt auto-setup
    const setupResult = await qbwcSetup.autoSetupQBWC();
    
    // Mark as attempted
    store.set('qbwcSetupAttempted', true);
    
    if (setupResult.success) {
      // Show notification dialog
      dialog.showMessageBox(window, {
        type: 'info',
        title: 'QuickBooks Web Connector Setup',
        message: 'QuickBooks Web Connector Setup',
        detail: setupResult.message + '\n\nPassword: admin',
        buttons: ['OK', 'Open QB Web Connector'],
        defaultId: 0,
        cancelId: 0
      }).then((response) => {
        if (response.response === 1 && checkResult.path) {
          // Open QB Web Connector
          const { shell } = require('electron');
          shell.openPath(checkResult.path).catch(err => {
            log.error('Failed to open QB Web Connector:', err);
          });
        }
      }).catch(err => {
        log.error('Error showing QBWC setup dialog:', err);
      });
    } else {
      log.warn('QBWC auto-setup failed:', setupResult.message);
      // Show error dialog
      dialog.showMessageBox(window, {
        type: 'warning',
        title: 'QuickBooks Web Connector Setup',
        message: 'Auto-setup Failed',
        detail: setupResult.message + '\n\nYou can manually add the application from the Tools menu.',
        buttons: ['OK', 'Manual Setup'],
        defaultId: 0,
        cancelId: 0
      }).then((response) => {
        if (response.response === 1) {
          // Open QWC file manually
          const qbwcSetup = require('./qbwc-setup');
          const qwcPath = qbwcSetup.getQWCFilePath();
          if (qwcPath) {
            const { shell } = require('electron');
            shell.openPath(qwcPath).catch(err => {
              log.error('Failed to open QWC file:', err);
            });
          }
        }
      }).catch(err => {
        log.error('Error showing QBWC error dialog:', err);
      });
    }
  } catch (error) {
    log.error('Error during QBWC auto-setup:', error);
    store.set('qbwcSetupAttempted', true);
  }
}

function showErrorPage(window, message) {
  const errorHtml = `
    <!DOCTYPE html>
    <html>
    <head>
      <title>Error - Sync Accounting Desktop</title>
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
          padding: 2rem;
          border-radius: 8px;
          box-shadow: 0 2px 10px rgba(0,0,0,0.1);
          max-width: 600px;
          text-align: center;
        }
        h1 { color: #dc3545; margin-top: 0; }
        p { color: #666; line-height: 1.6; }
        .log-path {
          background: #f8f9fa;
          padding: 1rem;
          border-radius: 4px;
          margin-top: 1rem;
          font-family: monospace;
          font-size: 0.9rem;
          text-align: left;
        }
      </style>
    </head>
    <body>
      <div class="error-container">
        <h1>⚠️ Application Error</h1>
        <p>${message}</p>
        <div class="log-path">
          <strong>Log file location:</strong><br>
          ${app.getPath('userData')}/logs/main.log
        </div>
        <p style="margin-top: 1rem; font-size: 0.9rem;">
          Please check the log file for more details or contact support.
        </p>
      </div>
    </body>
    </html>
  `;
  window.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(errorHtml)}`);
}

function createWindow() {
  log.info('Creating main window...');

  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false, // Disable sandbox to allow file:// protocol loading
      webSecurity: false, // Disable web security to allow loading from file:// and ASAR
      allowRunningInsecureContent: false,
      experimentalFeatures: true // Enable experimental features for better ES module support
    },
    icon: path.join(__dirname, '../resources/icons/icon.png'),
    show: true, // Show immediately so user knows app is starting
    titleBarStyle: 'default'
  });
  
  // Window is already shown (show: true), just focus when ready
  mainWindow.once('ready-to-show', () => {
    mainWindow.focus();
    log.info('Main window ready and focused');
    
    // Auto-setup QB Web Connector on first launch (Windows only)
    if (process.platform === 'win32') {
      // Wait a bit longer to ensure everything is loaded
      setTimeout(() => {
        log.info('Triggering QBWC auto-setup check...');
        checkAndSetupQBWC(mainWindow).catch(err => {
          log.error('Auto-setup check failed:', err);
        });
      }, 3000); // Wait 3 seconds for window to fully load
    } else {
      log.info('QBWC auto-setup skipped: Not on Windows');
    }
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
      log.error('Frontend build not found in any expected location.');
      log.error('Checked paths:', possiblePaths);
      const errorMsg = `Frontend build not found. Checked:\n${possiblePaths.map(p => `  - ${p}`).join('\n')}\n\nSee logs at: ${app.getPath('userData')}/logs/main.log`;
      showErrorPage(mainWindow, errorMsg);
    }
  }

  // Handle window closed
  mainWindow.on('closed', () => {
    mainWindow = null;
    log.info('Main window closed');
  });

  // Handle navigation errors
  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription, validatedURL, isMainFrame) => {
    log.error(`Failed to load: ${errorCode} - ${errorDescription} (URL: ${validatedURL}, MainFrame: ${isMainFrame})`);
    if (isMainFrame) {
      showErrorPage(mainWindow, `Failed to load page: ${errorDescription}\n\nError Code: ${errorCode}\nURL: ${validatedURL}`);
    }
  });

  // Handle console messages from renderer
  mainWindow.webContents.on('console-message', (event, level, message, line, sourceId) => {
    const levelMap = { 0: 'log', 1: 'info', 2: 'warning', 3: 'error' };
    log[levelMap[level] || 'info'](`[Renderer] ${message} (${sourceId}:${line})`);
  });

  // Handle uncaught JavaScript errors
  mainWindow.webContents.on('uncaught-exception', (event, error) => {
    log.error(`[Renderer] Uncaught exception: ${error.message}`);
    log.error(`[Renderer] Stack: ${error.stack}`);
  });

  // Log when page finishes loading
  mainWindow.webContents.on('did-finish-load', () => {
    log.info('Page finished loading');
  });

  // Log when DOM is ready
  mainWindow.webContents.on('dom-ready', () => {
    log.info('DOM ready');
    
    // Enable dev tools automatically for debugging blank screen issue
    // TODO: Remove or make configurable in production
    setTimeout(() => {
      mainWindow.webContents.openDevTools();
      log.info('DevTools opened for debugging');
    }, 1000);
    
    // Inject error handlers to catch JavaScript errors
    mainWindow.webContents.executeJavaScript(`
      (function() {
        const originalError = console.error;
        const originalLog = console.log;
        console.error = function(...args) {
          originalError.apply(console, args);
          // Errors will be logged via console-message event
        };
        console.log = function(...args) {
          originalLog.apply(console, args);
          // Logs will be captured via console-message event
        };
        window.addEventListener('error', (event) => {
          console.error('Global error:', event.error, event.filename, event.lineno, event.message);
        });
        window.addEventListener('unhandledrejection', (event) => {
          console.error('Unhandled promise rejection:', event.reason);
        });
        // Check if React root exists and scripts loaded
        setTimeout(() => {
          const root = document.getElementById('root');
          const scripts = Array.from(document.querySelectorAll('script[src]'));
          console.log('Scripts found:', scripts.map(s => ({ src: s.src, loaded: s.readyState, type: s.type })));
          
          if (root && root.children.length === 0) {
            console.error('⚠️ React root is empty - React may not have mounted');
            console.error('Root element:', root);
            console.error('Scripts status:', scripts.map(s => ({
              src: s.src,
              readyState: s.readyState,
              error: s.onerror ? 'Has error handler' : 'No error handler'
            })));
          } else if (root && root.children.length > 0) {
            console.log('✓ React appears to have mounted');
          }
        }, 3000);
      })();
    `).catch(err => log.warn('Could not inject error handlers:', err));
    
    // Check for script loading errors after a delay
    setTimeout(() => {
      mainWindow.webContents.executeJavaScript(`
        (function() {
          const scripts = document.querySelectorAll('script');
          const failedScripts = [];
          scripts.forEach(script => {
            if (script.src && !script.dataset.loaded) {
              failedScripts.push(script.src);
            }
          });
          if (failedScripts.length > 0) {
            console.error('Scripts failed to load:', failedScripts);
          }
        })();
      `).catch(() => {});
    }, 1000);
  });

  // Enable dev tools with F12 or Ctrl+Shift+I (for debugging)
  mainWindow.webContents.on('before-input-event', (event, input) => {
    if (input.key === 'F12' || (input.control && input.shift && input.key === 'I')) {
      if (mainWindow.webContents.isDevToolsOpened()) {
        mainWindow.webContents.closeDevTools();
      } else {
        mainWindow.webContents.openDevTools();
      }
    }
  });

  return mainWindow;
}

// App event handlers
app.whenReady().then(() => {
  log.info('App ready, creating window...');
  try {
    setupIpcHandlers();
    createWindow();
    setupMenu(mainWindow);

    // Check for auto-start monitoring
    const Store = require('electron-store');
    const store = new Store({ name: 'settings' });
    const autoStart = store.get('autoStartMonitoring', false);
    const monitoredDirectory = store.get('monitoredDirectory', '');
    
    if (autoStart && monitoredDirectory) {
      // Auto-start will be handled by the frontend when it loads
      // The frontend will call initializeMonitor and startMonitoring
      log.info('Auto-start monitoring enabled, will start when frontend loads');
    }

    // macOS: Re-create window when dock icon is clicked
    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
      }
    });
  } catch (error) {
    log.error('Failed to initialize app:', error);
    // Show error dialog
    dialog.showErrorBox(
      'Application Error',
      `Failed to start the application:\n\n${error.message}\n\nCheck the log file for details:\n${log.transports.file.getFile().path}`
    );
    app.quit();
  }
}).catch((error) => {
  log.error('App ready failed:', error);
  dialog.showErrorBox(
    'Application Error',
    `Failed to initialize the application:\n\n${error.message}\n\nCheck the log file for details:\n${log.transports.file.getFile().path}`
  );
  app.quit();
});

// Quit when all windows are closed (except on macOS)
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    log.info('All windows closed, quitting app');
    stopLocalServer().then(() => {
      app.quit();
    }).catch((error) => {
      log.error('Error stopping local server:', error);
      app.quit();
    });
  }
});

// Handle uncaught exceptions
process.on('uncaughtException', (error) => {
  log.error('Uncaught Exception:', error);
  if (mainWindow && !mainWindow.isDestroyed()) {
    dialog.showErrorBox(
      'Application Error',
      `An unexpected error occurred:\n\n${error.message}\n\nCheck the log file for details:\n${log.transports.file.getFile().path}`
    );
  }
  // Don't quit immediately - let user see the error
});

// Handle unhandled promise rejections
process.on('unhandledRejection', (reason, promise) => {
  log.error('Unhandled Rejection at:', promise, 'reason:', reason);
  if (mainWindow && !mainWindow.isDestroyed()) {
    dialog.showErrorBox(
      'Application Error',
      `An unexpected error occurred:\n\n${reason}\n\nCheck the log file for details:\n${log.transports.file.getFile().path}`
    );
  }
});

// Stop local server on app quit
app.on('before-quit', () => {
  stopLocalServer();
});

// Security: Prevent new window creation
app.on('web-contents-created', (event, contents) => {
  contents.on('new-window', (event, navigationUrl) => {
    event.preventDefault();
    log.warn(`Blocked new window to: ${navigationUrl}`);
  });
});

// Handle certificate errors (for development)
if (process.env.NODE_ENV === 'development') {
  app.on('certificate-error', (event, webContents, url, error, certificate, callback) => {
    if (url.includes('localhost') || url.includes('127.0.0.1')) {
      event.preventDefault();
      callback(true);
    } else {
      callback(false);
    }
  });
}

// Export for use in other modules
module.exports = { mainWindow };

