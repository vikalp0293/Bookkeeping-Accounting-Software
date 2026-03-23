/**
 * Auto-Sync Manager
 * Automatically starts sync service when transactions are queued
 */

const log = require('./logger');
const Store = require('electron-store');

// Must match main.js store name so we read the same config (apiToken, workspaceId, companyFile)
const store = new Store({
  name: 'sync-accounting-qbsdk-settings'
});

class AutoSyncManager {
  constructor(startSyncCallback, isSyncRunningCallback) {
    this.startSyncCallback = startSyncCallback;
    this.isSyncRunningCallback = isSyncRunningCallback;
    this.checkInterval = null;
    this.isRunning = false;
  }

  /**
   * Start auto-sync monitoring
   * Checks for queued transactions and auto-starts sync if configured
   */
  start() {
    if (this.isRunning) {
      return;
    }

    const autoStartEnabled = store.get('autoStartSync', true); // Default to true
    if (!autoStartEnabled) {
      log.info('Auto-sync is disabled');
      return;
    }

    log.info('Starting auto-sync manager...');
    this.isRunning = true;

    // Check every 10 seconds for queued transactions
    this.checkInterval = setInterval(() => {
      this.checkAndStartSync();
    }, 10000); // Check every 10 seconds

    // Also check immediately
    this.checkAndStartSync();
  }

  /**
   * Stop auto-sync monitoring
   */
  stop() {
    if (this.checkInterval) {
      clearInterval(this.checkInterval);
      this.checkInterval = null;
    }
    this.isRunning = false;
    log.info('Auto-sync manager stopped');
  }

  /**
   * Trigger immediate sync check (called after transactions are queued)
   */
  async triggerImmediateCheck() {
    log.info('Triggering immediate sync check...');
    await this.checkAndStartSync();
  }

  /**
   * Check for queued transactions and start sync if needed
   */
  async checkAndStartSync() {
    try {
      // Prefer access_token (fresh JWT from login); fallback to apiToken
      const apiToken = store.get('access_token') || store.get('apiToken');
      const backendUrl = store.get('backendUrl');
      const companyFile = store.get('companyFile');
      const workspaceAccountName = store.get('workspaceAccountName');

      if (!apiToken || !companyFile) {
        const missing = [];
        if (!apiToken) missing.push('apiToken/access_token');
        if (!companyFile) missing.push('companyFile');
        log.warn(`Auto-sync skipped: missing config in desktop Settings: ${missing.join(', ')}. Set them in app Settings.`);
        return;
      }

      // Resolve workspace ID from backend so we use the current user's workspace (avoids 403 when
      // store has stale workspaceId from a different user or old session)
      let workspaceId = store.get('workspaceId');
      try {
        const axios = require('axios');
        const defaultWorkspaceUrl = `${(backendUrl || '').replace(/\/$/, '')}/api/v1/workspaces/default`;
        const res = await axios.get(defaultWorkspaceUrl, {
          headers: { Authorization: `Bearer ${apiToken}` },
          timeout: 8000
        });
        if (res.data && res.data.id != null) {
          workspaceId = res.data.id;
          if (Number(store.get('workspaceId')) !== Number(workspaceId)) {
            log.info(`Using current user's workspace from API: ${workspaceId} (store had ${store.get('workspaceId')})`);
            store.set('workspaceId', workspaceId);
          }
        }
      } catch (err) {
        const msg = err.response ? `${err.response.status} ${err.response.statusText}` : err.message;
        log.warn(`Could not fetch default workspace: ${msg}; using store workspaceId=${workspaceId}`);
      }

      if (!workspaceId) {
        log.warn('Auto-sync skipped: no workspace ID (set Settings and save, or log in again).');
        return;
      }

      const config = {
        backendUrl,
        apiToken,
        workspaceId,
        companyFile,
        workspaceAccountName
      };

      // Check if sync is already running
      if (this.isSyncRunningCallback && this.isSyncRunningCallback()) {
        log.info('Sync already running, skipping auto-start');
        return;
      }

      // Check backend for queued transactions
      const axios = require('axios');
      const url = `${config.backendUrl}/api/v1/qb-queue/list`;
      const headers = {
        'Authorization': `Bearer ${config.apiToken}`,
        'Content-Type': 'application/json'
      };
      const params = {
        workspace_id: config.workspaceId,
        status: 'queued',
        limit: 1
      };

      try {
        log.info(`Checking for queued transactions: ${url} workspace_id=${config.workspaceId} status=queued`);
        const response = await axios.get(url, { headers, params, timeout: 10000 });
        const data = response.data;
        const queuedCount = data.count ?? (data.transactions ? data.transactions.length : 0);

        if (queuedCount > 0) {
          log.info(`Found ${queuedCount} queued transactions, auto-starting sync...`);

          if (this.startSyncCallback) {
            try {
              log.info('Calling startSyncCallback...');
              const result = await this.startSyncCallback(config);
              log.info(`startSyncCallback result: ${JSON.stringify(result)}`);
              if (result && !result.success) {
                const errorMsg = `Failed to start sync service: ${result.error || 'Unknown error'}`;
                log.error(errorMsg);
              } else {
                log.info('Sync service started successfully');
              }
            } catch (error) {
              log.error(`Error starting sync service: ${error.message}`, error);
            }
          } else {
            log.warn('startSyncCallback is not set!');
          }
        } else {
          log.info('No queued transactions found (count=0), sync not started');
        }
      } catch (error) {
        const msg = error.response ? `${error.response.status} ${error.response.statusText}` : error.message;
        log.warn(`Auto-sync check failed (list API): ${msg}`);
      }
    } catch (error) {
      log.error(`Error in auto-sync check: ${error.message}`);
    }
  }
}

module.exports = AutoSyncManager;

