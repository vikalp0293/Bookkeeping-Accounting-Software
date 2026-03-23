/**
 * Storage utility - abstracts localStorage (web) and electron-store (desktop)
 * Provides synchronous API for web, async API for Electron
 */

import { isElectron, electronAPI } from './electron-api';

// Storage interface
class Storage {
  constructor() {
    this.isElectron = isElectron();
    this.settings = null;
    this.settingsPromise = null;
  }

  async init() {
    if (this.isElectron && !this.settingsPromise) {
      // Load settings from Electron
      this.settingsPromise = electronAPI.getSettings().then(settings => {
        this.settings = settings || {};
        return this.settings;
      }).catch(error => {
        console.error('Failed to load Electron settings:', error);
        this.settings = {};
        return this.settings;
      });
      await this.settingsPromise;
    }
  }

  // Synchronous getItem for web compatibility
  getItem(key) {
    if (this.isElectron) {
      // For Electron, return from cached settings (must call init first)
      if (this.settings === null) {
        console.warn('Storage not initialized. Call init() first or use getItemAsync()');
        return null;
      }
      return this.settings[key] || null;
    } else {
      // Get from localStorage (synchronous)
      const value = localStorage.getItem(key);
      try {
        return value ? JSON.parse(value) : null;
      } catch {
        return value;
      }
    }
  }

  // Async getItem for Electron
  async getItemAsync(key) {
    if (this.isElectron) {
      if (!this.settings) {
        await this.init();
      }
      return this.settings[key] || null;
    } else {
      // For web, use synchronous version
      return this.getItem(key);
    }
  }

  // Synchronous setItem for web compatibility
  setItem(key, value) {
    if (this.isElectron) {
      // For Electron, queue the update (must call init first)
      if (this.settings === null) {
        console.warn('Storage not initialized. Call init() first or use setItemAsync()');
        return;
      }
      this.settings[key] = value;
      // Save asynchronously in background
      electronAPI.saveSettings(this.settings).catch(error => {
        console.error('Failed to save settings:', error);
      });
    } else {
      // Save to localStorage (synchronous)
      const stringValue = typeof value === 'string' ? value : JSON.stringify(value);
      localStorage.setItem(key, stringValue);
    }
  }

  // Async setItem for Electron
  async setItemAsync(key, value) {
    if (this.isElectron) {
      if (!this.settings) {
        await this.init();
      }
      this.settings[key] = value;
      await electronAPI.saveSettings(this.settings);
    } else {
      // For web, use synchronous version
      this.setItem(key, value);
    }
  }

  // Synchronous removeItem for web compatibility
  removeItem(key) {
    if (this.isElectron) {
      if (this.settings === null) {
        console.warn('Storage not initialized. Call init() first or use removeItemAsync()');
        return;
      }
      delete this.settings[key];
      // Save asynchronously in background
      electronAPI.saveSettings(this.settings).catch(error => {
        console.error('Failed to save settings:', error);
      });
    } else {
      // Remove from localStorage (synchronous)
      localStorage.removeItem(key);
    }
  }

  // Async removeItem for Electron
  async removeItemAsync(key) {
    if (this.isElectron) {
      if (!this.settings) {
        await this.init();
      }
      delete this.settings[key];
      await electronAPI.saveSettings(this.settings);
    } else {
      // For web, use synchronous version
      this.removeItem(key);
    }
  }

  // Synchronous clear for web compatibility
  clear() {
    if (this.isElectron) {
      if (this.settings === null) {
        console.warn('Storage not initialized. Call init() first or use clearAsync()');
        return;
      }
      this.settings = {};
      // Save asynchronously in background
      electronAPI.saveSettings({}).catch(error => {
        console.error('Failed to save settings:', error);
      });
    } else {
      // Clear localStorage (synchronous)
      localStorage.clear();
    }
  }

  // Async clear for Electron
  async clearAsync() {
    if (this.isElectron) {
      this.settings = {};
      await electronAPI.saveSettings({});
    } else {
      // For web, use synchronous version
      this.clear();
    }
  }
}

// Create singleton instance
const storage = new Storage();

// Initialize on import (for Electron) - don't block
if (isElectron()) {
  storage.init().catch(error => {
    console.error('Failed to initialize storage:', error);
  });
}

export default storage;

