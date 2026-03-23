const { app, Menu, shell } = require('electron');
const log = require('./logger').log;

/**
 * Create application menu
 */
function setupMenu(mainWindow) {
  const template = [
    {
      label: 'File',
      submenu: [
        {
          label: 'Settings',
          accelerator: 'CmdOrCtrl+,',
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.send('menu:open-settings');
            }
          }
        },
        { type: 'separator' },
        {
          label: 'Exit',
          accelerator: process.platform === 'darwin' ? 'Cmd+Q' : 'Ctrl+Q',
          click: () => {
            app.quit();
          }
        }
      ]
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo', label: 'Undo' },
        { role: 'redo', label: 'Redo' },
        { type: 'separator' },
        { role: 'cut', label: 'Cut' },
        { role: 'copy', label: 'Copy' },
        { role: 'paste', label: 'Paste' },
        { role: 'selectAll', label: 'Select All' }
      ]
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload', label: 'Reload' },
        { role: 'forceReload', label: 'Force Reload' },
        { role: 'toggleDevTools', label: 'Toggle Developer Tools' },
        { type: 'separator' },
        { role: 'resetZoom', label: 'Actual Size' },
        { role: 'zoomIn', label: 'Zoom In' },
        { role: 'zoomOut', label: 'Zoom Out' },
        { type: 'separator' },
        { role: 'togglefullscreen', label: 'Toggle Full Screen' }
      ]
    },
    {
      label: 'Tools',
      submenu: [
        {
          label: 'View Logs',
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.send('menu:open-logs');
            }
          }
        },
        {
          label: 'Open Logs Folder',
          click: () => {
            const logPath = require('path').join(app.getPath('userData'), 'logs');
            shell.openPath(logPath).catch(err => {
              log.error('Failed to open logs folder:', err);
            });
          }
        },
        { type: 'separator' },
        {
          label: 'Open QuickBooks Web Connector Config',
          click: async () => {
            const qbwcSetup = require('./qbwc-setup');
            const qwcPath = qbwcSetup.getQWCFilePath();
            
            if (qwcPath) {
              shell.openPath(qwcPath).catch(err => {
                log.error('Failed to open QWC file:', err);
              });
            } else {
              log.error('QWC file not found');
            }
          }
        },
        {
          label: 'Open Resources Folder',
          click: () => {
            const path = require('path');
            const fs = require('fs');
            let resourcesPath;
            if (process.env.NODE_ENV === 'development') {
              resourcesPath = path.join(__dirname, '../resources');
            } else {
              // Try app.asar/resources first
              const asarResources = path.join(app.getAppPath(), 'resources');
              if (fs.existsSync(asarResources)) {
                resourcesPath = asarResources;
              } else {
                // Fallback to process.resourcesPath
                resourcesPath = process.resourcesPath;
              }
            }
            shell.openPath(resourcesPath).catch(err => {
              log.error('Failed to open resources folder:', err);
            });
          }
        }
      ]
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'User Guide',
          click: () => {
            shell.openExternal('https://your-docs-url.com/user-guide');
          }
        },
        {
          label: 'Troubleshooting',
          click: () => {
            shell.openExternal('https://your-docs-url.com/troubleshooting');
          }
        },
        { type: 'separator' },
        {
          label: 'About',
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.send('menu:show-about');
            }
          }
        }
      ]
    }
  ];

  // macOS specific menu adjustments
  if (process.platform === 'darwin') {
    template.unshift({
      label: app.getName(),
      submenu: [
        { role: 'about', label: 'About ' + app.getName() },
        { type: 'separator' },
        { role: 'services', label: 'Services' },
        { type: 'separator' },
        { role: 'hide', label: 'Hide ' + app.getName() },
        { role: 'hideOthers', label: 'Hide Others' },
        { role: 'unhide', label: 'Show All' },
        { type: 'separator' },
        { role: 'quit', label: 'Quit ' + app.getName() }
      ]
    });

    // Window menu
    template[4].submenu = [
      { role: 'close', label: 'Close' },
      { role: 'minimize', label: 'Minimize' },
      { role: 'zoom', label: 'Zoom' },
      { type: 'separator' },
      { role: 'front', label: 'Bring All to Front' }
    ];
  }

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);

  log.info('Application menu created');
}

module.exports = { setupMenu };

