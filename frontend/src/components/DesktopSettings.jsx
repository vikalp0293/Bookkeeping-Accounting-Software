/**
 * Desktop Settings Component
 * Shows desktop-specific settings when running in Electron
 */

import { useState, useEffect } from 'react';
import { isElectron, electronAPI } from '../utils/electron-api';
import { workspacesAPI } from '../utils/api';
import storage from '../utils/storage';
import Card from './Card';
import Button from './Button';

const DesktopSettings = () => {
  const [settings, setSettings] = useState({
    monitoredDirectory: '',
    autoStartMonitoring: false,
  });
  const [workspace, setWorkspace] = useState(null);
  const [quickbooksAccountName, setQuickbooksAccountName] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [monitoringStatus, setMonitoringStatus] = useState(null);
  const [hasAutoStarted, setHasAutoStarted] = useState(false);
  const [companyFile, setCompanyFile] = useState('');
  const [quickbooksDirectory, setQuickbooksDirectory] = useState('');
  const [companyFilesList, setCompanyFilesList] = useState([]);
  const [companyAccountMap, setCompanyAccountMap] = useState({});
  const [accountForSelectedCompany, setAccountForSelectedCompany] = useState('');

  useEffect(() => {
    if (isElectron()) {
      loadSettings();
      loadWorkspace();
      loadMonitoringStatus();
      initializeMonitor();
      loadSdkConfig();
      // Poll monitoring status periodically
      const statusInterval = setInterval(() => {
        loadMonitoringStatus();
      }, 2000); // Every 2 seconds

      return () => {
        clearInterval(statusInterval);
      };
    }
  }, []);

  // Auto-start monitoring if enabled (only once on mount)
  useEffect(() => {
    if (isElectron() && !hasAutoStarted && settings.autoStartMonitoring && settings.monitoredDirectory && !monitoringStatus?.isMonitoring) {
      setHasAutoStarted(true);
      // Small delay to ensure everything is initialized
      const timer = setTimeout(() => {
        handleStartMonitoring();
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [settings.autoStartMonitoring, settings.monitoredDirectory, hasAutoStarted, monitoringStatus]);

  const loadSettings = async () => {
    try {
      const savedSettings = await electronAPI.getSettings();
      if (savedSettings) {
        setSettings(savedSettings);
      }
    } catch (error) {
      console.error('Failed to load settings:', error);
    }
  };

  const loadWorkspace = async () => {
    try {
      const workspaceData = await workspacesAPI.getDefaultWorkspace();
      if (workspaceData) {
        setWorkspace(workspaceData);
        setQuickbooksAccountName(workspaceData.quickbooks_account_name || '');
        // SDK app: persist token + workspaceId to Electron store so sync can run
        const token = await storage.getItemAsync('access_token');
        if (token && electronAPI.saveSettings) {
          const saved = await electronAPI.getSettings().catch(() => ({}));
          await electronAPI.saveSettings({ ...saved, apiToken: token, workspaceId: workspaceData.id });
        }
      }
    } catch (error) {
      console.error('Failed to load workspace:', error);
    }
  };

  // SDK app exposes getConfig/saveConfig on window.electronAPI (not on our wrapper)
  const hasSdkConfig = typeof window !== 'undefined' && window.electronAPI && typeof window.electronAPI.getConfig === 'function';

  const loadSdkConfig = async () => {
    if (!hasSdkConfig) return;
    try {
      const config = await window.electronAPI.getConfig();
      // Backend is the source of truth for workspace + per-company account map.
      // If Electron config is empty/stale (common after switching users), hydrate from backend.
      let backendWorkspace = null;
      try {
        backendWorkspace = await workspacesAPI.getDefaultWorkspace();
      } catch (_) {}
      const backendMap = (backendWorkspace && backendWorkspace.company_account_map && typeof backendWorkspace.company_account_map === 'object')
        ? backendWorkspace.company_account_map
        : {};

      if (config) {
        setCompanyFile(config.companyFile || '');
        setQuickbooksDirectory(config.quickbooksDirectory || '');
        const localMap = (config.companyAccountMap && typeof config.companyAccountMap === 'object') ? config.companyAccountMap : {};
        const effectiveMap = (localMap && Object.keys(localMap).length > 0) ? localMap : backendMap;
        setCompanyAccountMap(effectiveMap || {});
        setAccountForSelectedCompany((effectiveMap && config.companyFile) ? (effectiveMap[config.companyFile] ?? '') : '');

        // If backend has a map but local config doesn't, persist it locally so the UI is consistent.
        if (Object.keys(backendMap).length > 0 && Object.keys(localMap).length === 0 && window.electronAPI.saveConfig) {
          try {
            await window.electronAPI.saveConfig({
              ...config,
              companyAccountMap: backendMap,
            });
          } catch (e) {
            console.warn('Failed to hydrate local companyAccountMap from backend:', e?.message || e);
          }
        }

        if (config.quickbooksDirectory && window.electronAPI.listCompanyFiles) {
          const res = await window.electronAPI.listCompanyFiles(config.quickbooksDirectory);
          if (res?.success && Array.isArray(res.files)) setCompanyFilesList(res.files);
        }
      }
    } catch (e) {
    }
  };

  const handleSaveSdkConfig = async () => {
    if (!hasSdkConfig) return;
    setLoading(true);
    setMessage('');
    try {
      const token = await storage.getItemAsync('access_token');
      const config = await window.electronAPI.getConfig().catch(() => ({}));
      const nextMap = { ...(config.companyAccountMap || {}), [companyFile.trim()]: accountForSelectedCompany.trim() };
      if (!accountForSelectedCompany.trim()) delete nextMap[companyFile.trim()];
      await window.electronAPI.saveConfig({
        backendUrl: config.backendUrl || 'https://dev-sync-api.kylientlabs.com',
        apiToken: token || config.apiToken,
        workspaceId: workspace?.id ?? config.workspaceId,
        companyFile: companyFile.trim(),
        quickbooksDirectory: quickbooksDirectory.trim(),
        workspaceAccountName: quickbooksAccountName || config.workspaceAccountName,
        companyAccountMap: nextMap,
      });
      if (workspace?.id) {
        try {
          await workspacesAPI.updateWorkspace(workspace.id, { company_account_map: nextMap });
        } catch (e) {
          console.error('Failed to persist company account map to backend:', e);
        }
      }
      setMessage('QuickBooks SDK settings saved. Sync to QuickBooks can now run.');
    } catch (error) {
      setMessage(`Failed to save: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectCompanyFile = async () => {
    const result = await electronAPI.selectFile();
    if (result?.success && result.path) setCompanyFile(result.path);
  };

  // Pick folder containing .QBW (avoids "file in use" when QuickBooks has the file open)
  const handleSelectCompanyFileFolder = async () => {
    const result = await electronAPI.selectDirectory();
    if (result?.success && result.path) {
      const sep = electronAPI.getPlatform() === 'win32' ? '\\' : '/';
      const folder = result.path.replace(/[\\/]+$/, '');
      setCompanyFile(folder + sep);
    }
  };

  // Multi-company: select QuickBooks directory and scan for .qbw files
  const handleSelectQbDirectory = async () => {
    if (!window.electronAPI.selectQbDirectory || !window.electronAPI.listCompanyFiles) return;
    const result = await window.electronAPI.selectQbDirectory();
    if (!result?.success || !result.path) return;
    setQuickbooksDirectory(result.path);
    const res = await window.electronAPI.listCompanyFiles(result.path);
    if (res?.success && Array.isArray(res.files)) {
      setCompanyFilesList(res.files);
      if (res.files.length > 0 && !companyFile) setCompanyFile(res.files[0].path);
    } else {
      setCompanyFilesList([]);
    }
  };

  // Refresh company list from current directory
  const refreshCompanyList = async () => {
    if (!quickbooksDirectory || !window.electronAPI.listCompanyFiles) return;
    const res = await window.electronAPI.listCompanyFiles(quickbooksDirectory);
    if (res?.success && Array.isArray(res.files)) setCompanyFilesList(res.files);
  };

  const loadMonitoringStatus = async () => {
    try {
      const result = await electronAPI.getMonitoringStatus();
      if (result.success) {
        setMonitoringStatus(result.status);
      }
    } catch (error) {
      console.error('Failed to load monitoring status:', error);
    }
  };

  const initializeMonitor = async () => {
    try {
      // Get auth token and workspace ID
      const token = await storage.getItemAsync('access_token');
      const workspace = await workspacesAPI.getDefaultWorkspace();
      
      if (token && workspace) {
        const savedSettings = await electronAPI.getSettings();
        await electronAPI.initializeMonitor({
          backendUrl: savedSettings?.backendUrl || 'https://dev-sync-api.kylientlabs.com',
          authToken: token,
          workspaceId: workspace.id
        });
      }
    } catch (error) {
      console.error('Failed to initialize monitor:', error);
    }
  };

  const handleSelectDirectory = async () => {
    try {
      const result = await electronAPI.selectDirectory();
      if (result.success) {
        setSettings({ ...settings, monitoredDirectory: result.path });
        setMessage('');
      }
    } catch (error) {
      setMessage(`Error selecting directory: ${error.message}`);
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage('');

    try {
      // Save desktop settings (folder, auto-start)
      await electronAPI.saveSettings(settings);
      
      // Save workspace settings (QuickBooks account name)
      if (workspace && workspace.id) {
        await workspacesAPI.updateWorkspace(workspace.id, {
          quickbooks_account_name: quickbooksAccountName || null
        });
        // Reload workspace to get updated data
        await loadWorkspace();
      }
      
      setMessage('Settings saved successfully!');
      
      // If monitoring directory changed and monitoring is active, restart it
      if (monitoringStatus?.isMonitoring && settings.monitoredDirectory) {
        await handleStartMonitoring();
      }
    } catch (error) {
      setMessage(`Error saving settings: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleStartMonitoring = async () => {
    if (!settings.monitoredDirectory) {
      setMessage('Please select a directory to monitor first');
      return;
    }

    setLoading(true);
    setMessage('');

    try {
      // Get auth token and workspace ID
      const token = await storage.getItemAsync('access_token');
      const workspace = await workspacesAPI.getDefaultWorkspace();
      
      if (!token) {
        setMessage('Error: Please log in first');
        setLoading(false);
        return;
      }

      if (!workspace || !workspace.id) {
        setMessage('Error: Failed to load workspace');
        setLoading(false);
        return;
      }

      // Initialize monitor with current settings
      await electronAPI.initializeMonitor({
        backendUrl: (await electronAPI.getSettings())?.backendUrl || 'https://dev-sync-api.kylientlabs.com',
        authToken: token,
        workspaceId: workspace.id
      });

      // Start monitoring
      const result = await electronAPI.startMonitoring(settings.monitoredDirectory);
      
      if (result.success) {
        await loadMonitoringStatus();
        setMessage('Folder monitoring started successfully!');
      } else {
        setMessage(`Error: ${result.error || 'Failed to start monitoring'}`);
      }
    } catch (error) {
      setMessage(`Error starting monitoring: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleStopMonitoring = async () => {
    setLoading(true);
    setMessage('');

    try {
      await electronAPI.stopMonitoring();
      await loadMonitoringStatus();
      setMessage('Folder monitoring stopped');
    } catch (error) {
      setMessage(`Error stopping monitoring: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  if (!isElectron()) {
    return null;
  }

  return (
    <div className="space-y-6">
      {/* QuickBooks SDK: company file (required for sync) */}
      {hasSdkConfig && (
        <Card title="QuickBooks SDK Sync" subtitle="Required for Sync to QuickBooks">
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                QuickBooks directory
              </label>
              <p className="text-xs text-gray-500 mb-1">
                Select the folder that contains your .QBW company files. The app will list them and you choose which one to use for sync.
              </p>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={quickbooksDirectory}
                  onChange={(e) => setQuickbooksDirectory(e.target.value)}
                  placeholder="C:\Users\...\QuickBooks"
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-lg"
                />
                <Button type="button" variant="secondary" onClick={handleSelectQbDirectory}>
                  Select folder
                </Button>
                {quickbooksDirectory && (
                  <Button type="button" variant="secondary" onClick={refreshCompanyList}>
                    Refresh list
                  </Button>
                )}
              </div>
            </div>
            {companyFilesList.length > 0 && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Default company for sync
                </label>
                <select
                  value={companyFile}
                  onChange={(e) => {
                    const path = e.target.value;
                    setCompanyFile(path);
                    setAccountForSelectedCompany(companyAccountMap[path] ?? '');
                  }}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                >
                  {companyFilesList.map((f) => (
                    <option key={f.path} value={f.path}>
                      {f.name}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-xs text-gray-500">
                  This company file is used when you start sync or when auto-sync runs.
                </p>
                <div className="mt-3">
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    QuickBooks account for this company
                  </label>
                  <input
                    type="text"
                    value={accountForSelectedCompany}
                    onChange={(e) => setAccountForSelectedCompany(e.target.value)}
                    placeholder={quickbooksAccountName || 'e.g. Checking (or leave blank to use workspace default)'}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    Bank account in this company&apos;s Chart of Accounts for checks/deposits. If blank, the workspace default below is used. Set this when you use different companies so each syncs to the correct account.
                  </p>
                </div>
                <p className="mt-2 text-xs text-amber-600">
                  If you change the default company, set the account for that company above so sync uses the right QuickBooks account.
                </p>

                {/* Multi-company overview table */}
                <div className="mt-4">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm font-medium text-gray-700">Configured companies</p>
                    <p className="text-xs text-gray-500">
                      Accounts are read from saved mappings. To edit, select a company above, set the account, then Save.
                    </p>
                  </div>
                  <div className="border border-gray-200 rounded-lg overflow-hidden">
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-3 py-2 text-left text-xs font-semibold text-gray-600">Company file</th>
                          <th className="px-3 py-2 text-left text-xs font-semibold text-gray-600">Account</th>
                          <th className="px-3 py-2 text-left text-xs font-semibold text-gray-600">Default</th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-100">
                        {companyFilesList.map((f) => {
                          const account = (companyAccountMap && companyAccountMap[f.path]) ? String(companyAccountMap[f.path]) : '';
                          const isDefault = f.path === companyFile;
                          return (
                            <tr key={f.path} className={isDefault ? 'bg-blue-50' : ''}>
                              <td className="px-3 py-2 text-sm text-gray-800">
                                <div className="font-medium">{f.name || (f.path.split(/[/\\]/).pop() || f.path)}</div>
                                <div className="text-xs text-gray-500 break-all">{f.path}</div>
                              </td>
                              <td className="px-3 py-2 text-sm text-gray-800">
                                {account ? (
                                  <span className="inline-flex items-center px-2 py-1 rounded-md bg-green-50 text-green-700 border border-green-200 text-xs">
                                    {account}
                                  </span>
                                ) : (
                                  <span className="text-xs text-amber-700 bg-amber-50 border border-amber-200 px-2 py-1 rounded-md">
                                    Not set
                                  </span>
                                )}
                              </td>
                              <td className="px-3 py-2 text-sm text-gray-800">
                                {isDefault ? (
                                  <span className="text-xs font-semibold text-blue-700">Yes</span>
                                ) : (
                                  <span className="text-xs text-gray-500">No</span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}
            {companyFile && companyFilesList.length === 0 && (
              <div className="mb-3">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  QuickBooks account for this company
                </label>
                <input
                  type="text"
                  value={accountForSelectedCompany}
                  onChange={(e) => setAccountForSelectedCompany(e.target.value)}
                  placeholder={quickbooksAccountName || 'e.g. Checking (or leave blank to use workspace default)'}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                />
                <p className="mt-1 text-xs text-gray-500">
                  Bank account in this company&apos;s Chart of Accounts. If blank, the workspace default is used.
                </p>
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {companyFilesList.length > 0 ? 'Company file path (or override above)' : 'QuickBooks company file path (.QBW)'}
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={companyFile}
                  onChange={(e) => setCompanyFile(e.target.value)}
                  placeholder="C:\Users\...\Company.qbw"
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-lg"
                />
                <Button type="button" variant="secondary" onClick={handleSelectCompanyFileFolder}>
                  Select folder
                </Button>
                <Button type="button" variant="secondary" onClick={handleSelectCompanyFile}>
                  Browse...
                </Button>
              </div>
              <p className="mt-1 text-xs text-gray-500">
                Open QuickBooks and your company file first. Sync uses the path above.
              </p>
              {companyFile.trim() && !companyFile.trim().toLowerCase().endsWith('.qbw') && (
                <p className="mt-1 text-xs text-amber-600">
                  Use the QuickBooks company file path ending in <strong>.QBW</strong>, not .DSN or other files.
                </p>
              )}
            </div>
            <Button
              type="button"
              variant="primary"
              onClick={handleSaveSdkConfig}
              disabled={loading}
            >
              {loading ? 'Saving...' : 'Save SDK settings'}
            </Button>
          </div>
        </Card>
      )}

      {/* Folder Monitoring Settings */}
      <Card 
        title="Desktop Settings" 
        subtitle="Configure folder monitoring"
      >
        <form onSubmit={handleSave} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Folder to Monitor
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={settings.monitoredDirectory}
              onChange={(e) => setSettings({ ...settings, monitoredDirectory: e.target.value })}
              placeholder="C:\Users\YourName\Documents\Bank Statements"
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg"
              required
            />
            <Button
              type="button"
              variant="secondary"
              onClick={handleSelectDirectory}
            >
              Browse...
            </Button>
          </div>
          <p className="mt-1 text-xs text-gray-500">
            The local folder where you&apos;ll place PDF files for automatic processing
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            QuickBooks Account Name
          </label>
          <input
            type="text"
            value={quickbooksAccountName}
            onChange={(e) => setQuickbooksAccountName(e.target.value)}
            placeholder="e.g., Huntington X4497"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          />
          <p className="mt-1 text-xs text-gray-500">
            The QuickBooks account name where all transactions will be synced. This account must already exist in QuickBooks.
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <input
            type="checkbox"
            id="autoStart"
            checked={settings.autoStartMonitoring}
            onChange={(e) => setSettings({ ...settings, autoStartMonitoring: e.target.checked })}
            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
          />
          <label htmlFor="autoStart" className="text-sm font-medium text-gray-700">
            Automatically start monitoring when app launches
          </label>
        </div>

        {/* Monitoring Status */}
        {monitoringStatus && (
          <div className="p-3 rounded-lg bg-gray-50 border border-gray-200">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-700">
                  Monitoring Status
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  {monitoringStatus.isMonitoring ? (
                    <span className="text-green-600">● Active - Watching: {monitoringStatus.monitoredPath || settings.monitoredDirectory || 'No directory set'}</span>
                  ) : (
                    <span className="text-gray-500">○ Stopped</span>
                  )}
                </p>
                {monitoringStatus.queueLength > 0 && (
                  <p className="text-xs text-gray-500 mt-1">
                    {monitoringStatus.queueLength} file(s) queued for upload
                  </p>
                )}
                {monitoringStatus.isUploading && (
                  <p className="text-xs text-blue-500 mt-1">
                    Uploading files...
                  </p>
                )}
              </div>
              <div className="flex gap-2">
                {monitoringStatus.isMonitoring ? (
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={handleStopMonitoring}
                    disabled={loading}
                  >
                    Stop
                  </Button>
                ) : (
                  <Button
                    type="button"
                    variant="primary"
                    onClick={handleStartMonitoring}
                    disabled={loading || !settings.monitoredDirectory}
                  >
                    Start
                  </Button>
                )}
              </div>
            </div>
          </div>
        )}

        {message && (
          <div
            className={`p-3 rounded-lg ${
              message.includes('success') || message.includes('started')
                ? 'bg-green-50 text-green-700'
                : 'bg-red-50 text-red-700'
            }`}
          >
            {message}
          </div>
        )}

        <div className="flex gap-3">
          <Button type="submit" variant="primary" disabled={loading}>
            {loading ? 'Saving...' : 'Save Settings'}
          </Button>
        </div>
      </form>
      </Card>
    </div>
  );
};

export default DesktopSettings;

