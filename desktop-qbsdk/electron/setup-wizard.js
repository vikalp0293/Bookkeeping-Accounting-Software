/**
 * Setup Wizard
 * Automatically checks and installs all prerequisites for non-technical users
 */

const { dialog, shell } = require('electron');
const { spawn, exec } = require('child_process');
const fs = require('fs');
const path = require('path');
const log = require('./logger');
const pythonChecker = require('./python-checker');

class SetupWizard {
  constructor() {
    this.checks = {
      quickbooks: { installed: false, version: null, path: null },
      python: { installed: false, version: null, path: null },
      pythonDeps: { installed: false, missing: [] }
    };
  }

  /**
   * Run complete setup check
   */
  async runSetupCheck() {
    log.info('Running setup wizard...');
    
    const results = {
      quickbooks: await this.checkQuickBooks(),
      python: await this.checkPython(),
      pythonDeps: await this.checkPythonDependencies(),
      allReady: false
    };

    results.allReady = results.quickbooks.installed && 
                       results.python.installed && 
                       results.pythonDeps.installed;

    return results;
  }

  /**
   * Check if QuickBooks Desktop is installed or running
   */
  async checkQuickBooks() {
    return new Promise((resolve) => {
      // First, try PowerShell to find any QuickBooks process (more reliable, case-insensitive)
      // Use single quotes in PowerShell command to avoid quote escaping issues
      const psCommand = "Get-Process | Where-Object {$_.ProcessName -like '*quickbooks*' -or $_.ProcessName -like '*qbw*'} | Select-Object -First 1 -Property ProcessName";
      exec('powershell -Command "' + psCommand + '"', 
        { timeout: 5000 }, 
        (error, stdout) => {
          if (!error && stdout && stdout.trim().length > 0) {
            log.info('QuickBooks detected as running (PowerShell check)');
            resolve({ 
              installed: true, 
              version: 'Running', 
              path: 'Running (process detected)' 
            });
            return;
          }

          // Fallback: Check multiple QuickBooks process names (more comprehensive)
          const processNames = ['QBW32.exe', 'QuickBooks.exe', 'QBW.EXE', 'qbw32.exe', 'QBW32', 'QuickBooks'];
          let checked = 0;
          let found = false;

          const checkProcess = (processName) => {
            exec(`tasklist /FI "IMAGENAME eq ${processName}" /FO CSV /NH`, { timeout: 3000 }, (error, stdout) => {
              checked++;
              
              if (!error && stdout && stdout.trim().length > 0 && !found) {
                // QuickBooks is running - definitely installed
                found = true;
                log.info(`QuickBooks detected as running (${processName})`);
                resolve({ 
                  installed: true, 
                  version: 'Running', 
                  path: 'Running (process detected)' 
                });
                return;
              }

              // If we've checked all processes and none are running, check installation paths
              if (checked === processNames.length && !found) {
                // Check installation paths
                const qbPaths = [
                  'C:\\Program Files\\Intuit\\QuickBooks',
                  'C:\\Program Files (x86)\\Intuit\\QuickBooks',
                  process.env.PROGRAMFILES ? path.join(process.env.PROGRAMFILES, 'Intuit', 'QuickBooks') : null,
                  process.env['PROGRAMFILES(X86)'] ? path.join(process.env['PROGRAMFILES(X86)'], 'Intuit', 'QuickBooks') : null
                ].filter(p => p !== null);

                let pathChecked = 0;
                let pathFound = false;
                let version = null;
                let qbPath = null;

                const checkPath = (index) => {
                  if (index >= qbPaths.length) {
                    resolve({ installed: pathFound, version, path: qbPath });
                    return;
                  }

                  const testPath = qbPaths[index];
                  fs.access(testPath, fs.constants.F_OK, (err) => {
                    pathChecked++;
                    
                    if (!err && !pathFound) {
                      // QuickBooks folder exists, check for QBW32.exe or QuickBooks.exe
                      const exeNames = ['QBW32.exe', 'QuickBooks.exe', 'QBW.EXE'];
                      let exeChecked = 0;
                      
                      const checkExe = (exeIndex) => {
                        if (exeIndex >= exeNames.length) {
                          // No executable found in this path, try next path
                          checkPath(index + 1);
                          return;
                        }
                        
                        const qbwExe = path.join(testPath, exeNames[exeIndex]);
                        fs.access(qbwExe, fs.constants.F_OK, (err2) => {
                          exeChecked++;
                          
                          if (!err2 && !pathFound) {
                            pathFound = true;
                            qbPath = testPath;
                            version = 'Detected';
                            resolve({ installed: true, version, path: qbPath });
                          } else if (exeChecked === exeNames.length) {
                            // All executables checked, try next path
                            checkPath(index + 1);
                          } else {
                            checkExe(exeIndex + 1);
                          }
                        });
                      };
                      
                      checkExe(0);
                    } else if (pathChecked === qbPaths.length && !pathFound) {
                      // All paths checked, nothing found
                      resolve({ installed: false, version: null, path: null });
                    } else if (pathChecked < qbPaths.length) {
                      // Try next path
                      checkPath(index + 1);
                    }
                  });
                };

                checkPath(0);
              }
            });
          };

          // Check all process names in parallel
          processNames.forEach(processName => checkProcess(processName));
        });
    });
  }

  /**
   * Check if Python is installed (bundled or system)
   */
  async checkPython() {
    // On Windows, prefer bundled Python (app uses it for QuickBooks COM)
    if (process.platform === 'win32') {
      const pythonExe = pythonChecker.getPythonExe();
      if (pythonExe && pythonExe.includes(path.sep) && fs.existsSync(pythonExe)) {
        log.info('Using bundled Python: ' + pythonExe);
        return { installed: true, version: 'Bundled', path: pythonExe };
      }
    }
    return new Promise((resolve) => {
      exec('python --version', (error, stdout, stderr) => {
        if (!error) {
          const version = stdout.trim() || stderr.trim();
          exec('where python', (err, pathOutput) => {
            const pythonPath = err ? null : pathOutput.split('\n')[0].trim();
            resolve({ installed: true, version, path: pythonPath });
          });
        } else {
          exec('python3 --version', (error3, stdout3) => {
            if (!error3) {
              const version = stdout3.trim();
              exec('where python3', (err, pathOutput) => {
                const pythonPath = err ? null : pathOutput.split('\n')[0].trim();
                resolve({ installed: true, version, path: pythonPath });
              });
            } else {
              resolve({ installed: false, version: null, path: null });
            }
          });
        }
      });
    });
  }

  /**
   * Check if Python dependencies are installed (uses bundled or system Python)
   */
  async checkPythonDependencies() {
    const pythonExe = pythonChecker.getPythonExe();
    const checkScript = `
import sys
missing = []
try:
    import win32com.client
except ImportError:
    missing.append('pywin32')
try:
    import psutil
except ImportError:
    missing.append('psutil')
try:
    import requests
except ImportError:
    missing.append('requests')

if missing:
    print(','.join(missing))
    sys.exit(1)
else:
    print('OK')
    sys.exit(0)
`;
    return new Promise((resolve) => {
      const proc = spawn(pythonExe, ['-c', checkScript], { shell: false });
      let stdout = '';
      let stderr = '';
      proc.stdout.on('data', (d) => { stdout += d.toString(); });
      proc.stderr.on('data', (d) => { stderr += d.toString(); });
      proc.on('close', (code) => {
        if (code !== 0) {
          resolve({ installed: false, missing: ['pywin32', 'psutil', 'requests'] });
        } else {
          const output = stdout.trim();
          if (output === 'OK') {
            resolve({ installed: true, missing: [] });
          } else {
            const missing = output.split(',').filter(m => m);
            resolve({ installed: false, missing: missing.length ? missing : ['pywin32', 'psutil', 'requests'] });
          }
        }
      });
      proc.on('error', () => {
        resolve({ installed: false, missing: ['pywin32', 'psutil', 'requests'] });
      });
    });
  }

  /**
   * Install Python dependencies (uses shared auto-installer: bundled Python + wheels when available)
   */
  async installPythonDependencies() {
    const autoInstaller = require('./auto-installer');
    const result = await autoInstaller.autoInstallPythonDependencies();
    if (result.success) {
      return;
    }
    throw new Error(result.message || 'Failed to install Python dependencies');
  }

  /**
   * Show setup dialog with options
   */
  async showSetupDialog(results) {
    const missing = [];
    let message = 'Setup Check Results:\n\n';

    if (!results.quickbooks.installed) {
      missing.push('QuickBooks Desktop');
      message += '❌ QuickBooks Desktop: NOT INSTALLED\n';
      message += '   Please install QuickBooks Desktop Pro 2018 or later.\n\n';
    } else {
      message += `✓ QuickBooks Desktop: INSTALLED\n`;
      message += `   Path: ${results.quickbooks.path}\n\n`;
    }

    if (!results.python.installed) {
      missing.push('Python');
      message += '❌ Python: NOT INSTALLED\n';
      message += '   Python 3.8+ is required.\n\n';
    } else {
      message += `✓ Python: INSTALLED\n`;
      message += `   Version: ${results.python.version}\n\n`;
    }

    if (!results.pythonDeps.installed) {
      missing.push('Python Dependencies');
      message += '❌ Python Dependencies: MISSING\n';
      message += `   Missing: ${results.pythonDeps.missing.join(', ')}\n\n`;
    } else {
      message += '✓ Python Dependencies: INSTALLED\n\n';
    }

    if (missing.length === 0) {
      message += '✅ All requirements are met! You can start syncing.';
      dialog.showMessageBox({
        type: 'info',
        title: 'QB Accounting SDK - Setup Complete',
        message: 'Setup Check Complete',
        detail: message,
        buttons: ['OK']
      });
      return { canProceed: true };
    }

    // Show what's missing and offer to fix
    const buttons = ['Cancel'];
    if (results.python.installed && !results.pythonDeps.installed) {
      buttons.unshift('Install Dependencies');
    }
    if (!results.python.installed) {
      buttons.unshift('Download Python');
    }
    if (!results.quickbooks.installed) {
      buttons.unshift('Download QuickBooks');
    }

    const response = await dialog.showMessageBox({
      type: 'warning',
      title: 'QB Accounting SDK - Setup Required',
      message: 'Some requirements are missing',
      detail: message + '\nWould you like to install them now?',
      buttons: buttons,
      defaultId: buttons.length - 1
    });

    if (response.response === 0) {
      // First button clicked
      if (buttons[0] === 'Install Dependencies') {
        try {
          await this.installPythonDependencies();
          dialog.showMessageBox({
            type: 'info',
            title: 'Success',
            message: 'Python dependencies installed successfully!',
            detail: 'You can now start syncing.'
          });
          return { canProceed: true };
        } catch (error) {
          dialog.showErrorBox(
            'Installation Failed',
            `Failed to install Python dependencies:\n\n${error.message}\n\nPlease install them manually:\npip install -r requirements.txt`
          );
          return { canProceed: false };
        }
      } else if (buttons[0] === 'Download Python') {
        shell.openExternal('https://www.python.org/downloads/');
        return { canProceed: false };
      } else if (buttons[0] === 'Download QuickBooks') {
        shell.openExternal('https://quickbooks.intuit.com/desktop/');
        return { canProceed: false };
      }
    }

    return { canProceed: false };
  }

  /**
   * Auto-setup: Try to install everything automatically
   */
  async autoSetup() {
    log.info('Starting auto-setup...');
    const results = await this.runSetupCheck();

    if (results.allReady) {
      log.info('All requirements already met');
      return { success: true, message: 'All requirements are already installed' };
    }

    // Auto-install Python dependencies if Python is installed
    if (results.python.installed && !results.pythonDeps.installed) {
      try {
        log.info('Auto-installing Python dependencies...');
        await this.installPythonDependencies();
        results.pythonDeps = await this.checkPythonDependencies();
      } catch (error) {
        log.error(`Auto-install failed: ${error.message}`);
        return {
          success: false,
          message: `Auto-setup partially failed:\n\n${error.message}\n\nPlease install Python dependencies manually.`,
          results
        };
      }
    }

    // Check what's still missing
    const stillMissing = [];
    if (!results.quickbooks.installed) {
      stillMissing.push('QuickBooks Desktop (must be installed separately)');
    }
    if (!results.python.installed) {
      stillMissing.push('Python 3.8+ (must be installed separately)');
    }

    if (stillMissing.length > 0) {
      return {
        success: false,
        message: `The following must be installed manually:\n\n${stillMissing.join('\n')}\n\nAfter installing, restart the application.`,
        results
      };
    }

    return {
      success: true,
      message: 'Auto-setup completed successfully!',
      results
    };
  }
}

module.exports = new SetupWizard();


