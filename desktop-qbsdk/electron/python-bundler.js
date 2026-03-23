/**
 * Python Bundler
 * Handles bundled Python or embedded Python installer
 */

const { app } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn, exec, execSync, spawnSync } = require('child_process');
const log = require('./logger');
const https = require('https');
const { shell } = require('electron');

const PYTHON_VERSION = '3.11.9'; // Python version to bundle/download (32-bit for QuickBooks COM)
const PYTHON_INSTALLER_URL = `https://www.python.org/ftp/python/${PYTHON_VERSION}/python-${PYTHON_VERSION}.exe`; // 32-bit = no -amd64
const PYTHON_INSTALLER_FILENAME = `python-${PYTHON_VERSION}.exe`;

const PYTHON_EMBED_ZIP_BASENAME = 'python-embed-win32.zip';

/**
 * Path to extracted Python (when built on Mac, zip is extracted to userData on first run)
 */
function getUserDataPythonPortableDir() {
  return path.join(app.getPath('userData'), 'python-portable');
}

/**
 * Check if we have bundled Python (in resources or extracted in userData)
 */
function hasBundledPython() {
  const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
  
  if (isDev) {
    return false; // No bundled Python in dev
  }

  // Resources (Windows build) or extracted (Mac build)
  const inResources = path.join(process.resourcesPath, 'python-portable', 'python.exe');
  const inUserData = path.join(getUserDataPythonPortableDir(), 'python.exe');
  return fs.existsSync(inResources) || fs.existsSync(inUserData);
}

/**
 * Get Python executable path
 */
function getPythonPath() {
  // Prefer extracted userData (Mac-built installer), then resources (Windows-built)
  const userDataExe = path.join(getUserDataPythonPortableDir(), 'python.exe');
  if (fs.existsSync(userDataExe)) {
    return userDataExe;
  }
  const resourcesExe = path.join(process.resourcesPath, 'python-portable', 'python.exe');
  if (fs.existsSync(resourcesExe)) {
    return resourcesExe;
  }

  // Try to find Python in common locations.
  // On Windows, prefer 32-bit Python first (Program Files x86, LocalAppData) so COM works with 32-bit QuickBooks Desktop.
  const programFilesX86 = process.env['PROGRAMFILES(X86)'] || 'C:\\Program Files (x86)';
  const programFiles = process.env.PROGRAMFILES || 'C:\\Program Files';
  const localAppData = process.env.LOCALAPPDATA || '';
  const commonPaths = [
    // 32-bit first (QuickBooks Desktop is 32-bit; COM requires same bitness)
    path.join(programFilesX86, 'Python311', 'python.exe'),
    path.join(programFilesX86, 'Python310', 'python.exe'),
    path.join(programFilesX86, 'Python39', 'python.exe'),
    path.join(programFilesX86, 'Python38', 'python.exe'),
    path.join(localAppData, 'Programs', 'Python', 'Python311', 'python.exe'),
    path.join(localAppData, 'Programs', 'Python', 'Python310', 'python.exe'),
    path.join(localAppData, 'Programs', 'Python', 'Python39', 'python.exe'),
    path.join(localAppData, 'Programs', 'Python', 'Python38', 'python.exe'),
    // Then 64-bit
    path.join(programFiles, 'Python311', 'python.exe'),
    path.join(programFiles, 'Python310', 'python.exe'),
    path.join(programFiles, 'Python39', 'python.exe'),
    path.join(programFiles, 'Python38', 'python.exe'),
    'C:\\Python311\\python.exe',
    'C:\\Python310\\python.exe',
    'C:\\Python39\\python.exe',
    'C:\\Python38\\python.exe',
  ];

  // Check full paths first
  for (const pythonPath of commonPaths) {
    if (fs.existsSync(pythonPath)) {
      log.info(`Found Python at: ${pythonPath}`);
      // QuickBooks Desktop is 32-bit; 64-bit Python can cause "Could not start QuickBooks" at BeginSession
      if (process.platform === 'win32' && !pythonPath.includes('(x86)') && pythonPath.includes(programFiles)) {
        log.warn('Using 64-bit Python. If sync fails with "Could not start QuickBooks", install 32-bit Python from python.org and reinstall the app.');
      }
      return pythonPath;
    }
  }

  // Fallback to checking PATH (python, python3, py)
  // These will be resolved by the shell when spawning
  log.info('Python not found in common locations, using PATH lookup: python');
  return 'python';
}

/**
 * On Windows: if installer was built on Mac (zip only), extract zip to userData and set up Python.
 * Call this before starting sync so first-run users get Python ready.
 */
async function ensureBundledPythonReady() {
  if (process.platform !== 'win32') {
    return;
  }
  if (hasBundledPython()) {
    return; // Already have python-portable (resources or userData)
  }
  const zipPath = path.join(process.resourcesPath, PYTHON_EMBED_ZIP_BASENAME);
  if (!fs.existsSync(zipPath)) {
    return; // No zip (e.g. dev mode)
  }
  const userDataDir = getUserDataPythonPortableDir();
  if (fs.existsSync(path.join(userDataDir, 'python.exe'))) {
    return; // Already extracted
  }
  log.info('Extracting embedded Python from zip (first run)...');
  try {
    if (!fs.existsSync(userDataDir)) {
      fs.mkdirSync(userDataDir, { recursive: true });
    }
    // Extract using PowerShell
    const psCmd = `Expand-Archive -Path '${zipPath.replace(/'/g, "''")}' -DestinationPath '${userDataDir.replace(/'/g, "''")}' -Force`;
    execSync(`powershell -Command "${psCmd}"`, { stdio: 'inherit', timeout: 120000 });
    // Enable site-packages in ._pth
    const files = fs.readdirSync(userDataDir);
    const pthFile = files.find(f => f.endsWith('._pth'));
    if (pthFile) {
      const pthPath = path.join(userDataDir, pthFile);
      let content = fs.readFileSync(pthPath, 'utf-8');
      content = content.replace(/# ?import site/g, 'import site');
      fs.writeFileSync(pthPath, content);
    }
    const pythonExe = path.join(userDataDir, 'python.exe');
    // Download get-pip.py
    const getPipPath = path.join(userDataDir, 'get-pip.py');
    await new Promise((resolve, reject) => {
      const file = fs.createWriteStream(getPipPath);
      const onResponse = (res) => {
        if (res.statusCode === 301 || res.statusCode === 302) {
          https.get(res.headers.location, onResponse).on('error', reject);
          return;
        }
        res.pipe(file);
        file.on('finish', () => { file.close(); resolve(); });
      };
      https.get('https://bootstrap.pypa.io/get-pip.py', onResponse).on('error', reject);
    });
    spawnSync(pythonExe, [getPipPath], { cwd: userDataDir, stdio: 'inherit', timeout: 60000 });
    const requirementsPath = path.join(process.resourcesPath, 'python', 'requirements.txt');
    if (fs.existsSync(requirementsPath)) {
      spawnSync(pythonExe, ['-m', 'pip', 'install', '--no-cache-dir', '-r', requirementsPath], { cwd: userDataDir, stdio: 'inherit', timeout: 120000 });
    }
    log.info('Embedded Python ready at ' + userDataDir);
  } catch (err) {
    log.error('Failed to extract/setup embedded Python: ' + err.message);
    throw err;
  }
}

/**
 * Download Python installer
 */
async function downloadPythonInstaller(downloadPath) {
  return new Promise((resolve, reject) => {
    log.info(`Downloading Python installer to ${downloadPath}...`);
    
    const file = fs.createWriteStream(downloadPath);
    
    https.get(PYTHON_INSTALLER_URL, (response) => {
      if (response.statusCode === 302 || response.statusCode === 301) {
        // Follow redirect
        https.get(response.headers.location, (redirectResponse) => {
          redirectResponse.pipe(file);
          file.on('finish', () => {
            file.close();
            log.info('Python installer downloaded successfully');
            resolve();
          });
        }).on('error', reject);
      } else {
        response.pipe(file);
        file.on('finish', () => {
          file.close();
          log.info('Python installer downloaded successfully');
          resolve();
        });
      }
    }).on('error', (err) => {
      fs.unlink(downloadPath, () => {}); // Delete partial file
      reject(err);
    });
  });
}

/**
 * Install Python silently with "Add to PATH" option
 */
async function installPythonSilently(installerPath) {
  return new Promise((resolve, reject) => {
    log.info('Installing Python silently...');
    
    // Silent install with "Add Python to PATH" and "Install for all users"
    // /quiet = no UI
    // /prependpath = add to PATH
    // InstallAllUsers = 1 = install for all users
    const installArgs = [
      installerPath,
      '/quiet',
      'InstallAllUsers=1',
      'PrependPath=1',
      'Include_test=0'
    ];

    const install = spawn(installerPath, installArgs, {
      detached: true,
      stdio: 'ignore'
    });

    install.unref(); // Don't wait for it

    // Wait a bit then check if Python is available
    setTimeout(() => {
      exec('python --version', (error) => {
        if (!error) {
          log.info('Python installed successfully');
          resolve({ success: true });
        } else {
          // Python might need a restart to be in PATH
          log.warn('Python installer completed, but Python not yet in PATH (may need restart)');
          resolve({ success: true, needsRestart: true });
        }
      });
    }, 30000); // Wait 30 seconds for installation
  });
}

/**
 * Auto-install Python if not found
 */
async function autoInstallPython() {
  return new Promise(async (resolve, reject) => {
    // Check if Python is already installed
    exec('python --version', async (error) => {
      if (!error) {
        log.info('Python is already installed');
        resolve({ success: true, alreadyInstalled: true });
        return;
      }

      // Python not found - download and install
      const tempDir = app.getPath('temp');
      const installerPath = path.join(tempDir, PYTHON_INSTALLER_FILENAME);

      try {
        // Download installer
        await downloadPythonInstaller(installerPath);
        
        // Install silently
        const result = await installPythonSilently(installerPath);
        
        resolve(result);
      } catch (err) {
        log.error(`Failed to auto-install Python: ${err.message}`);
        reject(err);
      }
    });
  });
}

/**
 * Get Python installer path (if bundled)
 */
function getBundledPythonInstaller() {
  const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
  
  if (isDev) {
    return null;
  }

  const installerPath = path.join(process.resourcesPath, 'python-installer', PYTHON_INSTALLER_FILENAME);
  
  if (fs.existsSync(installerPath)) {
    return installerPath;
  }

  return null;
}

/**
 * Run bundled Python installer
 */
async function runBundledPythonInstaller() {
  const installerPath = getBundledPythonInstaller();
  
  if (!installerPath) {
    return { success: false, error: 'Python installer not bundled' };
  }

  try {
    log.info(`Running bundled Python installer: ${installerPath}`);
    
    // Run installer with UI (user-friendly for non-technical users)
    // But with "Add to PATH" pre-selected
    const install = spawn(installerPath, [
      '/passive', // Show progress bar but no user interaction needed
      'InstallAllUsers=1',
      'PrependPath=1',
      'Include_test=0'
    ], {
      detached: true,
      stdio: 'ignore'
    });

    install.unref();

    return { success: true, message: 'Python installer is running. Please complete the installation and restart the app.' };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

module.exports = {
  hasBundledPython,
  getPythonPath,
  ensureBundledPythonReady,
  autoInstallPython,
  getBundledPythonInstaller,
  runBundledPythonInstaller,
  PYTHON_INSTALLER_FILENAME
};


