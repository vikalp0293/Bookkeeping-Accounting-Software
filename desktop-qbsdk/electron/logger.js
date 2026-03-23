const log = require('electron-log');
const { app } = require('electron');
const path = require('path');

// Configure logging with unique app name to avoid conflicts
// This ensures logs go to a unique directory separate from web connector app
log.transports.file.resolvePathFn = () => {
  const userDataPath = app.getPath('userData');
  return path.join(userDataPath, 'logs', 'main.log');
};

log.transports.file.level = 'info';
log.transports.file.maxSize = 5 * 1024 * 1024; // 5MB
log.transports.console.level = 'info';

module.exports = log;

