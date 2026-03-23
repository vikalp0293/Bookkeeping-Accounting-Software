/**
 * Electron API wrapper
 * Provides access to Electron main process APIs
 */

// Check if running in Electron
export const isElectron = () => {
  return typeof window !== 'undefined' && window.electronAPI !== undefined;
};

// Get Electron API
export const getElectronAPI = () => {
  if (!isElectron()) {
    return null;
  }
  return window.electronAPI;
};

// Electron API wrapper functions
export const electronAPI = {
  // App info
  getVersion: async () => {
    const api = getElectronAPI();
    if (!api) return null;
    return api.getVersion();
  },

  getPlatform: () => {
    const api = getElectronAPI();
    if (!api) return null;
    return api.getPlatform();
  },

  // Settings
  getSettings: async () => {
    const api = getElectronAPI();
    if (!api) return null;
    return api.getSettings();
  },

  saveSettings: async (settings) => {
    const api = getElectronAPI();
    if (!api) return null;
    return api.saveSettings(settings);
  },

  // Directory monitoring
  initializeMonitor: async (settings) => {
    const api = getElectronAPI();
    if (!api) return null;
    return api.initializeMonitor(settings);
  },

  startMonitoring: async (directoryPath) => {
    const api = getElectronAPI();
    if (!api) return null;
    return api.startMonitoring(directoryPath);
  },

  stopMonitoring: async () => {
    const api = getElectronAPI();
    if (!api) return null;
    return api.stopMonitoring();
  },

  getMonitoringStatus: async () => {
    const api = getElectronAPI();
    if (!api) return null;
    return api.getMonitoringStatus();
  },

  // File operations
  selectDirectory: async () => {
    const api = getElectronAPI();
    if (!api) return null;
    return api.selectDirectory();
  },

  selectFile: async () => {
    const api = getElectronAPI();
    if (!api) return null;
    return api.selectFile();
  },

  // Logs
  getLogs: async (logType) => {
    const api = getElectronAPI();
    if (!api) return null;
    return api.getLogs(logType);
  },

  // QWC file operations
  getQwcPath: async () => {
    const api = getElectronAPI();
    if (!api) return null;
    return api.getQwcPath();
  },

  openQwcFolder: async () => {
    const api = getElectronAPI();
    if (!api) return null;
    return api.openQwcFolder();
  },

  openQwcFile: async () => {
    const api = getElectronAPI();
    if (!api) return null;
    return api.openQwcFile();
  },

  // QBWC auto-setup
  checkQBWCInstalled: async () => {
    const api = getElectronAPI();
    if (!api) return null;
    return api.checkQBWCInstalled();
  },
  autoSetupQBWC: async () => {
    const api = getElectronAPI();
    if (!api) return null;
    return api.autoSetupQBWC();
  },
  checkQBWCConfigured: async () => {
    const api = getElectronAPI();
    if (!api) return null;
    return api.checkQBWCConfigured();
  },
  resetQBWCSetupFlag: async () => {
    const api = getElectronAPI();
    if (!api) return null;
    return api.resetQBWCSetupFlag();
  },

  // Event listeners
  onFileUploaded: (callback) => {
    const api = getElectronAPI();
    if (!api) return () => {};
    api.onFileUploaded(callback);
    return () => api.removeAllListeners('file-uploaded');
  },

  onMonitoringStatusChanged: (callback) => {
    const api = getElectronAPI();
    if (!api) return () => {};
    api.onMonitoringStatusChanged(callback);
    return () => api.removeAllListeners('monitoring-status-changed');
  },

  onError: (callback) => {
    const api = getElectronAPI();
    if (!api) return () => {};
    api.onError(callback);
    return () => api.removeAllListeners('error');
  },

  // SDK-specific sync methods
  startSync: async (config) => {
    const api = getElectronAPI();
    if (!api || !api.startSync) return null;
    return api.startSync(config);
  },

  stopSync: async () => {
    const api = getElectronAPI();
    if (!api || !api.stopSync) return null;
    return api.stopSync();
  },

  getSyncStatus: async () => {
    const api = getElectronAPI();
    if (!api || !api.getSyncStatus) return null;
    return api.getSyncStatus();
  },

  triggerSyncCheck: async () => {
    const api = getElectronAPI();
    if (!api || !api.triggerSyncCheck) return null;
    return api.triggerSyncCheck();
  },
};

export default electronAPI;

