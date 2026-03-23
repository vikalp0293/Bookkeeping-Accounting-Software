/**
 * Python Environment Checker
 * Checks if Python is installed and dependencies are available.
 * When embedded Python is bundled (python-portable), uses that instead of system Python.
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const log = require('./logger');

/**
 * Get the Python executable to use (bundled if available, else system)
 */
function getPythonExe() {
  if (process.platform === 'win32') {
    try {
      const pythonBundler = require('./python-bundler');
      if (pythonBundler.hasBundledPython()) {
        const bundled = pythonBundler.getPythonPath();
        if (bundled && fs.existsSync(bundled)) {
          return bundled;
        }
      }
    } catch (e) {
      log.debug('python-bundler not available:', e.message);
    }
  }
  return process.platform === 'win32' ? 'python' : 'python3';
}

/**
 * Check if Python is installed (bundled or system)
 */
function checkPythonInstalled() {
  return new Promise((resolve) => {
    const pythonExe = getPythonExe();
    // shell: false so paths with spaces (e.g. C:\Program Files\...\python.exe) are not split
    const check = spawn(pythonExe, ['--version'], { shell: false });
    
    check.on('close', (code) => {
      resolve(code === 0);
    });
    
    check.on('error', () => {
      resolve(false);
    });
  });
}

/**
 * Check if Python dependencies are installed (uses bundled or system Python)
 */
function checkPythonDependencies() {
  return new Promise((resolve) => {
    const pythonExe = getPythonExe();
    // shell: false so paths with spaces (e.g. C:\Program Files\...\python.exe) are not split
    const check = spawn(pythonExe, ['-c', 'import win32com.client; import psutil; import requests'], {
      shell: false
    });
    
    check.on('close', (code) => {
      resolve(code === 0);
    });
    
    check.on('error', () => {
      resolve(false);
    });
  });
}

/**
 * Install Python dependencies (no-op when using bundled Python; they are pre-installed)
 */
function installPythonDependencies() {
  return new Promise((resolve, reject) => {
    try {
      const pythonBundler = require('./python-bundler');
      if (pythonBundler.hasBundledPython()) {
        log.info('Using bundled Python; dependencies are already installed');
        resolve();
        return;
      }
    } catch (e) {
      // continue to system pip install
    }

    const { app } = require('electron');
    const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
    let pythonDir;
    
    if (isDev) {
      pythonDir = path.join(__dirname, '../python');
    } else {
      pythonDir = path.join(process.resourcesPath, 'python');
    }
    
    const installScript = path.join(pythonDir, 'install_dependencies.bat');
    const pythonExe = getPythonExe();
    const requirementsFile = path.join(pythonDir, 'requirements.txt');

    // Prefer pip install -r requirements.txt so we use the same Python the app uses (no path-with-spaces or batch file issues)
    const usePip = fs.existsSync(requirementsFile);
    if (usePip) {
      log.info(`Installing Python dependencies from ${requirementsFile} (python: ${pythonExe})`);
      // Use shell: false so the requirements path (e.g. C:\Program Files\...\requirements.txt) is passed as one argument and not split on spaces
      const install = spawn(pythonExe, ['-m', 'pip', 'install', '-r', requirementsFile], {
        cwd: pythonDir,
        shell: false
      });
      install.stdout.on('data', (data) => {
        log.info(`pip: ${data.toString().trim()}`);
      });
      install.stderr.on('data', (data) => {
        log.error(`pip error: ${data.toString().trim()}`);
      });
      install.on('close', (code) => {
        if (code === 0) {
          log.info('Python dependencies installed successfully');
          resolve();
        } else {
          log.error(`Failed to install Python dependencies (exit code: ${code})`);
          reject(new Error(`pip install failed with code ${code}`));
        }
      });
      install.on('error', (err) => {
        log.error(`Failed to start pip install: ${err.message}`);
        reject(err);
      });
      return;
    }

    if (fs.existsSync(installScript)) {
      log.info(`Running install script: ${installScript}`);
      // Pass path as single argument (no extra quotes - they break cmd)
      const install = process.platform === 'win32'
        ? spawn('cmd', ['/c', installScript], { cwd: pythonDir, shell: false })
        : spawn(installScript, [], { cwd: pythonDir, shell: true });
      install.stdout.on('data', (data) => {
        log.info(`install: ${data.toString().trim()}`);
      });
      install.stderr.on('data', (data) => {
        log.error(`install error: ${data.toString().trim()}`);
      });
      install.on('close', (code) => {
        if (code === 0) {
          log.info('Python dependencies installed successfully');
          resolve();
        } else {
          log.error(`Failed to install Python dependencies (exit code: ${code})`);
          reject(new Error(`Install script failed with code ${code}`));
        }
      });
      install.on('error', (err) => {
        log.error(`Failed to start install script: ${err.message}`);
        reject(err);
      });
    } else {
      reject(new Error('No requirements.txt or install_dependencies.bat found'));
    }
  });
}

/**
 * Verify Python environment is ready (uses bundled Python when available)
 */
async function verifyPythonEnvironment() {
  log.info('Checking Python environment...');
  
  const pythonInstalled = await checkPythonInstalled();
  if (!pythonInstalled) {
    let hint = 'Please install Python 3.8+ from https://www.python.org/\nMake sure to check "Add Python to PATH" during installation.\n\n';
    try {
      const pythonBundler = require('./python-bundler');
      if (process.platform === 'win32' && pythonBundler.hasBundledPython()) {
        hint = 'Bundled Python was not found. Reinstall the app.\n\n';
      }
    } catch (e) { /* use default hint */ }
    throw new Error(
      'Python is not available.\n\n' + hint +
      'QB Accounting SDK requires Python to sync with QuickBooks Desktop.'
    );
  }
  
  log.info('Python is available');
  
  const depsInstalled = await checkPythonDependencies();
  if (!depsInstalled) {
    try {
      const pythonBundler = require('./python-bundler');
      if (pythonBundler.hasBundledPython()) {
        throw new Error(
          'Bundled Python is missing required packages. ' +
          'If the log shows "Microsoft Visual C++ 14.0 or greater is required", install Visual C++ Build Tools from https://visualstudio.microsoft.com/visual-cpp-build-tools/ ' +
          'or use an installer that includes pre-built wheels (rebuild with: npm run build:win).'
        );
      }
    } catch (e) {
      if (e.message.includes('Bundled Python')) throw e;
    }
    log.warn('Python dependencies not found, attempting to install...');
    try {
      await installPythonDependencies();
    } catch (err) {
      throw new Error(
        `Failed to install Python dependencies:\n${err.message}\n\n` +
        'Please run the installer manually or install dependencies with:\n' +
        'pip install -r requirements.txt'
      );
    }
  } else {
    log.info('Python dependencies are installed');
  }
  
  return true;
}

module.exports = {
  getPythonExe,
  checkPythonInstalled,
  checkPythonDependencies,
  installPythonDependencies,
  verifyPythonEnvironment
};

