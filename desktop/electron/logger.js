const log = require('electron-log');
const path = require('path');
const { app } = require('electron');

/**
 * Configure electron-log for the application
 */
function setupLogger() {
  // Configure file logging
  log.transports.file.level = 'info';
  log.transports.file.maxSize = 10 * 1024 * 1024; // 10MB
  log.transports.file.format = '[{y}-{m}-{d} {h}:{i}:{s}.{ms}] [{level}] {text}';
  
  // Set log file location
  const logPath = path.join(app.getPath('userData'), 'logs');
  log.transports.file.resolvePathFn = () => path.join(logPath, 'main.log');

  // Configure console logging
  log.transports.console.level = process.env.NODE_ENV === 'development' ? 'debug' : 'info';
  log.transports.console.format = '[{h}:{i}:{s}.{ms}] [{level}] {text}';

  // Log startup
  log.info('='.repeat(60));
  log.info('Sync Accounting Desktop - Starting');
  log.info(`Version: ${app.getVersion()}`);
  log.info(`Platform: ${process.platform}`);
  log.info(`Architecture: ${process.arch}`);
  log.info(`Node: ${process.versions.node}`);
  log.info(`Electron: ${process.versions.electron}`);
  log.info(`User Data: ${app.getPath('userData')}`);
  log.info('='.repeat(60));

  return log;
}

module.exports = { setupLogger, log };

