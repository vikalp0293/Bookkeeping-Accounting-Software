/**
 * Preload script - runs in isolated context before page loads
 * Provides secure bridge between renderer and main process
 */

const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld('electronAPI', {
  // App info
  getVersion: () => ipcRenderer.invoke('app:get-version'),
  getPlatform: () => process.platform,

  // Settings
  getSettings: () => ipcRenderer.invoke('settings:get'),
  saveSettings: (settings) => ipcRenderer.invoke('settings:save', settings),

  // Directory monitoring
  startMonitoring: (directoryPath) => ipcRenderer.invoke('monitor:start', directoryPath),
  stopMonitoring: () => ipcRenderer.invoke('monitor:stop'),
  getMonitoringStatus: () => ipcRenderer.invoke('monitor:status'),
  initializeMonitor: (settings) => ipcRenderer.invoke('monitor:initialize', settings),

  // File operations
  selectDirectory: () => ipcRenderer.invoke('file:select-directory'),
  selectFile: () => ipcRenderer.invoke('file:select-file'),

  // Logs
  getLogs: (logType) => ipcRenderer.invoke('logs:get', logType),

  // QWC file operations
  getQwcPath: () => ipcRenderer.invoke('qwc:get-path'),
  openQwcFolder: () => ipcRenderer.invoke('qwc:open-folder'),
  openQwcFile: () => ipcRenderer.invoke('qwc:open-file'),
  // QBWC auto-setup
  checkQBWCInstalled: () => ipcRenderer.invoke('qwc:check-installed'),
  autoSetupQBWC: () => ipcRenderer.invoke('qwc:auto-setup'),
  checkQBWCConfigured: () => ipcRenderer.invoke('qwc:check-configured'),
  resetQBWCSetupFlag: () => ipcRenderer.invoke('qwc:reset-setup-flag'),

  // Events (listen to main process events)
  onFileUploaded: (callback) => {
    ipcRenderer.on('file-uploaded', (event, data) => callback(data));
  },
  onMonitoringStatusChanged: (callback) => {
    ipcRenderer.on('monitoring-status-changed', (event, data) => callback(data));
  },
  onError: (callback) => {
    ipcRenderer.on('error', (event, error) => callback(error));
  },

  // Remove listeners
  removeAllListeners: (channel) => {
    ipcRenderer.removeAllListeners(channel);
  }
});

// Log that preload script loaded
console.log('Preload script loaded');

