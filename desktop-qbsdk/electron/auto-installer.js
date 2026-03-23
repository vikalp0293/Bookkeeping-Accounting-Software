/**
 * Auto-Installer for Python Dependencies
 * Automatically installs Python packages when app starts
 */

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const log = require('./logger');
const { app } = require('electron');

/**
 * Auto-install Python dependencies silently.
 * Uses the same Python as the app (bundled when available) so deps are installed for the runtime we use.
 */
async function autoInstallPythonDependencies() {
  return new Promise((resolve, reject) => {
    // Use same Python as sync (bundled path when available; else system 'python')
    let pythonExe;
    try {
      const pythonChecker = require('./python-checker');
      pythonExe = pythonChecker.getPythonExe();
    } catch (e) {
      pythonExe = process.platform === 'win32' ? 'python' : 'python3';
    }
    const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;

    let pythonDir;
    if (isDev) {
      pythonDir = path.join(__dirname, '../python');
    } else {
      pythonDir = path.join(process.resourcesPath, 'python');
    }

    const requirementsFile = path.join(pythonDir, 'requirements.txt');

    if (!fs.existsSync(requirementsFile)) {
      log.warn('requirements.txt not found, skipping auto-install');
      resolve({ success: false, message: 'requirements.txt not found' });
      return;
    }

    log.info('Auto-installing Python dependencies... (python: ' + pythonExe + ')');

    // Check if bundled wheels exist
    const wheelsDir = path.join(pythonDir, 'dependencies', 'wheels');
    const hasBundledWheels = fs.existsSync(wheelsDir) && fs.readdirSync(wheelsDir).some(f => f.endsWith('.whl'));

    let installArgs;
    if (hasBundledWheels) {
      log.info('Using bundled wheels for offline installation');
      installArgs = ['-m', 'pip', 'install', '--quiet', '--upgrade', '--no-index', '--find-links', wheelsDir, '-r', 'requirements.txt'];
    } else {
      log.info('No bundled wheels found, installing from PyPI (requires internet)');
      installArgs = ['-m', 'pip', 'install', '--quiet', '--upgrade', '-r', 'requirements.txt'];
    }

    // shell: false so paths with spaces (e.g. C:\Program Files\...\wheels) are not split by the shell
    const install = spawn(pythonExe, installArgs, {
      cwd: pythonDir,
      shell: false,
      stdio: ['ignore', 'pipe', 'pipe']
    });

    let output = '';
    install.stdout.on('data', (data) => {
      output += data.toString();
    });

    install.stderr.on('data', (data) => {
      output += data.toString();
    });

    install.on('close', (code) => {
      if (code === 0) {
        log.info('Python dependencies auto-installed successfully');
        resolve({ success: true });
      } else {
        log.warn(`Auto-install returned code ${code}, but continuing...`);
        const trimmed = output && output.trim();
        if (trimmed) {
          const toLog = trimmed.length > 2000 ? trimmed.slice(-2000) : trimmed;
          log.warn('pip output (last 2000 chars if truncated):', toLog);
        }
        resolve({ success: false, message: 'pip install failed', pipOutput: output });
      }
    });

    install.on('error', (err) => {
      log.warn(`Auto-install error: ${err.message}`);
      // Don't fail - user might need to install manually
      resolve({ success: false, message: err.message });
    });
  });
}

module.exports = { autoInstallPythonDependencies };


