/**
 * QuickBooks Web Connector Auto-Setup
 * Automatically detects and registers the .qwc file with QB Web Connector
 */

const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');
const { app, shell } = require('electron');
const log = require('./logger').log;

/**
 * Check if QuickBooks Web Connector is installed
 * @returns {Promise<{installed: boolean, path: string|null, error: string|null}>}
 */
async function checkQBWCInstalled() {
  if (process.platform !== 'win32') {
    return {
      installed: false,
      path: null,
      error: 'QuickBooks Web Connector is only available on Windows'
    };
  }

  // Common installation paths
  const commonPaths = [
    'C:\\Program Files (x86)\\Common Files\\Intuit\\QuickBooks\\QBWebConnector\\QBWebConnector.exe',
    'C:\\Program Files\\Common Files\\Intuit\\QuickBooks\\QBWebConnector\\QBWebConnector.exe'
  ];

  // Check if executable exists
  for (const qbwcPath of commonPaths) {
    if (fs.existsSync(qbwcPath)) {
      log.info(`QB Web Connector found at: ${qbwcPath}`);
      return {
        installed: true,
        path: qbwcPath,
        error: null
      };
    }
  }

  // Check Windows registry (optional - more complex, executable check is usually sufficient)
  try {
    const { execSync } = require('child_process');
    const regQuery = 'reg query "HKLM\\SOFTWARE\\Intuit\\QBWebConnector" /v InstallPath 2>nul';
    const result = execSync(regQuery, { encoding: 'utf-8', stdio: 'pipe' });
    if (result) {
      const match = result.match(/InstallPath\s+REG_SZ\s+(.+)/);
      if (match) {
        const installPath = match[1].trim();
        const exePath = path.join(installPath, 'QBWebConnector.exe');
        if (fs.existsSync(exePath)) {
          log.info(`QB Web Connector found via registry: ${exePath}`);
          return {
            installed: true,
            path: exePath,
            error: null
          };
        }
      }
    }
  } catch (error) {
    // Registry check failed, continue with other checks
    log.debug('Registry check failed (this is OK):', error.message);
  }

  log.warn('QB Web Connector not found');
  return {
    installed: false,
    path: null,
    error: 'QuickBooks Web Connector is not installed. Please install it from Intuit.'
  };
}

/**
 * Get the path to the .qwc file
 * @returns {string|null}
 */
function getQWCFilePath() {
  let qwcPath;
  
  if (process.env.NODE_ENV === 'development') {
    qwcPath = path.join(__dirname, '../resources/sync_accounting.qwc');
  } else {
    // In production, resources are outside app.asar
    // app.getAppPath() = .../resources/app.asar
    // process.resourcesPath = .../resources (parent of app.asar)
    // The .qwc file should be at: .../resources/sync_accounting.qwc
    
    // Log all paths for debugging
    log.info(`Looking for QWC file:`);
    log.info(`  - process.resourcesPath: ${process.resourcesPath}`);
    log.info(`  - app.getAppPath(): ${app.getAppPath()}`);
    
    // In electron-builder, extraResources are placed in process.resourcesPath
    // Try multiple possible locations
    
    // 1. process.resourcesPath (where extraResources are placed)
    const resourcesPath = path.join(process.resourcesPath, 'sync_accounting.qwc');
    log.info(`  - Checking (1): ${resourcesPath}`);
    
    if (fs.existsSync(resourcesPath)) {
      log.info(`✓ QWC file found at: ${resourcesPath}`);
      return resourcesPath;
    }
    
    // 2. Parent directory of app.asar (if app.asar is in resources folder)
    const appPath = app.getAppPath();
    log.info(`  - app.getAppPath(): ${appPath}`);
    
    if (appPath.endsWith('.asar')) {
      const appDir = path.dirname(appPath);
      const altPath1 = path.join(appDir, 'sync_accounting.qwc');
      log.info(`  - Checking (2): ${altPath1}`);
      
      if (fs.existsSync(altPath1)) {
        log.info(`✓ QWC file found at: ${altPath1}`);
        return altPath1;
      }
      
      // 3. Parent of parent (if app.asar is in resources/app.asar)
      const parentDir = path.dirname(appDir);
      const altPath2 = path.join(parentDir, 'sync_accounting.qwc');
      log.info(`  - Checking (3): ${altPath2}`);
      
      if (fs.existsSync(altPath2)) {
        log.info(`✓ QWC file found at: ${altPath2}`);
        return altPath2;
      }
    }
    
    // 4. Try app.getAppPath() parent directly
    const appDir = path.dirname(appPath);
    const altPath3 = path.join(appDir, '..', 'sync_accounting.qwc');
    log.info(`  - Checking (4): ${altPath3}`);
    
    if (fs.existsSync(altPath3)) {
      log.info(`✓ QWC file found at: ${altPath3}`);
      return altPath3;
    }
    
    // File not found - return null (don't try app.asar/resources as it won't work)
    log.error(`✗ QWC file not found in any location`);
    log.error(`  Checked:`);
    log.error(`    1. ${resourcesPath}`);
    if (appPath.endsWith('.asar')) {
      log.error(`    2. ${path.join(path.dirname(appPath), 'sync_accounting.qwc')}`);
    }
    return null;
  }

  // Development mode - check if file exists
  if (fs.existsSync(qwcPath)) {
    log.info(`✓ QWC file found at: ${qwcPath}`);
    return qwcPath;
  }

  log.error(`✗ QWC file not found at: ${qwcPath}`);
  return null;
}

/**
 * Automatically register the .qwc file with QB Web Connector
 * This opens the .qwc file, which triggers QB Web Connector to prompt the user to add it
 * @returns {Promise<{success: boolean, message: string, requiresUserAction: boolean}>}
 */
async function autoSetupQBWC() {
  log.info('Starting QB Web Connector auto-setup...');

  // Check if QB Web Connector is installed
  const qbwcCheck = await checkQBWCInstalled();
  if (!qbwcCheck.installed) {
    return {
      success: false,
      message: qbwcCheck.error || 'QuickBooks Web Connector is not installed',
      requiresUserAction: true,
      action: 'install_qbwc'
    };
  }

  // Get .qwc file path
  const qwcPath = getQWCFilePath();
  if (!qwcPath) {
    return {
      success: false,
      message: 'QWC configuration file not found. Please reinstall the application.',
      requiresUserAction: true,
      action: 'reinstall'
    };
  }

  try {
    // Verify file exists before trying to open
    if (!fs.existsSync(qwcPath)) {
      log.error(`QWC file does not exist at: ${qwcPath}`);
      return {
        success: false,
        message: `QWC file not found at: ${qwcPath}\n\nPlease ensure the file exists in the resources folder.`,
        requiresUserAction: true,
        action: 'file_not_found'
      };
    }

    // Open the .qwc file - this will trigger QB Web Connector to prompt the user
    // On Windows, double-clicking a .qwc file opens it with QB Web Connector
    log.info(`Opening QWC file: ${qwcPath}`);
    log.info(`File exists: ${fs.existsSync(qwcPath)}`);
    log.info(`File stats: ${JSON.stringify(fs.statSync(qwcPath))}`);
    
    await shell.openPath(qwcPath);

    // Wait a moment to ensure the file opens
    await new Promise(resolve => setTimeout(resolve, 1000));

    log.info('QWC file opened successfully. QB Web Connector should prompt to add the application.');
    
    return {
      success: true,
      message: 'QuickBooks Web Connector setup initiated. Please follow the prompts in QB Web Connector to complete setup.',
      requiresUserAction: true,
      action: 'complete_setup',
      qwcPath: qwcPath
    };
  } catch (error) {
    log.error('Failed to open QWC file:', error);
    return {
      success: false,
      message: `Failed to open QWC file: ${error.message}`,
      requiresUserAction: true,
      action: 'manual_setup'
    };
  }
}

/**
 * Check if QB Web Connector is already configured
 * This checks if the app is already registered in QB Web Connector
 * Note: This is a best-effort check - we can't directly query QB Web Connector's registry
 * @returns {Promise<{configured: boolean, message: string}>}
 */
async function checkQBWCConfigured() {
  // We can't directly check if the app is registered in QB Web Connector
  // The best we can do is check if QB Web Connector is installed
  const qbwcCheck = await checkQBWCInstalled();
  
  if (!qbwcCheck.installed) {
    return {
      configured: false,
      message: 'QuickBooks Web Connector is not installed'
    };
  }

  // We assume it's not configured and let the user verify
  // In a real scenario, you might check QB Web Connector's registry entries
  // or try to connect and see if authentication succeeds
  return {
    configured: false, // Always return false to allow re-setup
    message: 'Please verify in QB Web Connector if "Sync Accounting" is already added'
  };
}

module.exports = {
  checkQBWCInstalled,
  getQWCFilePath,
  autoSetupQBWC,
  checkQBWCConfigured
};

