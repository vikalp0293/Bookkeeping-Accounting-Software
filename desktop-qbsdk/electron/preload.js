const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // App info
  getVersion: () => ipcRenderer.invoke('app:get-version'),
  getPlatform: () => process.platform,

  // Settings (for frontend compatibility)
  getSettings: () => ipcRenderer.invoke('settings:get'),
  saveSettings: (settings) => ipcRenderer.invoke('settings:save', settings),

  // Config (SDK-specific)
  getConfig: () => ipcRenderer.invoke('get-config'),
  saveConfig: (config) => ipcRenderer.invoke('save-config', config),

  // QBWC stubs (shared DesktopSettings expects these; SDK app uses Python sync, not QBWC)
  getMonitoringStatus: () => Promise.resolve({ isMonitoring: false, status: 'sdk' }),
  initializeMonitor: () => Promise.resolve(),
  checkQBWCInstalled: () => Promise.resolve({ installed: false, configured: false }),

  // Sync service
  startSync: (config) => ipcRenderer.invoke('start-sync', config),
  stopSync: () => ipcRenderer.invoke('stop-sync'),
  getSyncStatus: () => ipcRenderer.invoke('get-sync-status'),
  triggerSyncCheck: () => ipcRenderer.invoke('trigger-sync-check'),
  
  // Python environment
  checkPython: () => ipcRenderer.invoke('check-python'),
  installPythonDeps: () => ipcRenderer.invoke('install-python-deps'),
  
  // Setup wizard
  runSetupCheck: () => ipcRenderer.invoke('setup:check'),
  autoSetup: () => ipcRenderer.invoke('setup:auto'),
  showSetupDialog: (results) => ipcRenderer.invoke('setup:dialog', results),
  
  // File operations (for frontend compatibility)
  selectDirectory: () => ipcRenderer.invoke('file:select-directory'),
  selectFile: () => ipcRenderer.invoke('file:select-file'),
  selectQbDirectory: () => ipcRenderer.invoke('file:select-qb-directory'),
  listCompanyFiles: (dirPath) => ipcRenderer.invoke('qb:list-company-files', dirPath),
  
  // Logs (for frontend compatibility)
  getLogs: (logType) => ipcRenderer.invoke('logs:get', logType),
  
  // Events
  onSyncLog: (callback) => {
    ipcRenderer.on('sync-log', (event, data) => callback(data));
  },
  onSyncError: (callback) => {
    ipcRenderer.on('sync-error', (event, data) => callback(data));
  },
  onSyncStopped: (callback) => {
    ipcRenderer.on('sync-stopped', (event, code) => callback(code));
  },
  onFileUploaded: (callback) => {
    ipcRenderer.on('file-uploaded', (event, data) => callback(data));
  },
  onMonitoringStatusChanged: (callback) => {
    ipcRenderer.on('monitoring-status-changed', (event, data) => callback(data));
  },
  onError: (callback) => {
    ipcRenderer.on('error', (event, error) => callback(error));
  },
  removeAllListeners: (channel) => {
    ipcRenderer.removeAllListeners(channel);
  },
});

