const http = require('http');
const fs = require('fs');
const path = require('path');
const { URL } = require('url');
const log = require('./logger');

let server = null;
let serverPort = null;

/**
 * Start a local HTTP server to serve the frontend files
 * This is necessary because ES modules don't work with file:// protocol in Electron
 */
function startLocalServer(frontendPath) {
  return new Promise((resolve, reject) => {
    if (server) {
      log.info(`Local server already running on port ${serverPort}`);
      resolve(`http://localhost:${serverPort}`);
      return;
    }

    const startPort = 5175; // SDK app starts from 5175 to avoid conflict with web connector (5174)
    let attempts = 0;
    const maxAttempts = 10;

    const tryPort = (port) => {
      attempts++;
      log.info(`Attempting to start server on port ${port} (attempt ${attempts}/${maxAttempts})...`);
      
      const testServer = http.createServer();
      testServer.listen(port, () => {
        testServer.close(() => {
          // Port is available, start the real server
          server = http.createServer((req, res) => {
            const parsedUrl = new URL(req.url, `http://localhost:${port}`);
            let filePath = parsedUrl.pathname;

            // Default to index.html
            if (filePath === '/') {
              filePath = '/index.html';
            }

            // Remove leading slash
            const fullPath = path.join(frontendPath, filePath);

            // Security: prevent directory traversal
            const resolvedPath = path.resolve(fullPath);
            const resolvedFrontend = path.resolve(frontendPath);
            if (!resolvedPath.startsWith(resolvedFrontend)) {
              res.writeHead(403, { 'Content-Type': 'text/plain' });
              res.end('Forbidden');
              return;
            }

            // Determine content type
            const ext = path.extname(fullPath).toLowerCase();
            const contentTypes = {
              '.html': 'text/html',
              '.js': 'application/javascript',
              '.mjs': 'application/javascript',
              '.json': 'application/json',
              '.css': 'text/css',
              '.png': 'image/png',
              '.jpg': 'image/jpeg',
              '.jpeg': 'image/jpeg',
              '.gif': 'image/gif',
              '.svg': 'image/svg+xml',
              '.ico': 'image/x-icon',
              '.woff': 'font/woff',
              '.woff2': 'font/woff2',
              '.ttf': 'font/ttf',
              '.eot': 'application/vnd.ms-fontobject',
              '.map': 'application/json',
            };

            const contentType = contentTypes[ext] || 'application/octet-stream';

            // Read and serve file
            fs.readFile(fullPath, (err, data) => {
              if (err) {
                if (err.code === 'ENOENT') {
                  log.warn(`File not found: ${fullPath}`);
                  res.writeHead(404, { 'Content-Type': 'text/plain' });
                  res.end('File not found');
                } else {
                  log.error(`Error reading file ${fullPath}: ${err.message}`);
                  res.writeHead(500, { 'Content-Type': 'text/plain' });
                  res.end('Internal server error');
                }
                return;
              }

              // Set CORS headers for local development
              res.writeHead(200, {
                'Content-Type': contentType,
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization',
              });

              res.end(data);
            });
          });

          server.listen(port, '127.0.0.1', () => {
            serverPort = port;
            const url = `http://localhost:${port}`;
            log.info(`Local HTTP server started on ${url}`);
            log.info(`Serving files from: ${frontendPath}`);
            resolve(url);
          });

          server.on('error', (err) => {
            log.error(`Server error: ${err.message}`);
            reject(err);
          });
        });
      });

      testServer.on('error', (err) => {
        if (err.code === 'EADDRINUSE') {
          // Port is in use, try next port
          if (attempts < maxAttempts) {
            log.info(`Port ${port} is in use, trying next port...`);
            tryPort(port + 1);
          } else {
            const errorMsg = `Failed to find available port after ${maxAttempts} attempts (tried ports ${startPort}-${port}). Please close other applications or restart your computer.`;
            log.error(errorMsg);
            reject(new Error(errorMsg));
          }
        } else {
          reject(err);
        }
      });
    };

    // Start from port 5175 to avoid conflicts with web connector app (uses 5174)
    tryPort(startPort);
  });
}

/**
 * Stop the local HTTP server
 */
function stopLocalServer() {
  return new Promise((resolve) => {
    if (server) {
      server.close(() => {
        log.info('Local HTTP server stopped');
        server = null;
        serverPort = null;
        resolve();
      });
    } else {
      resolve();
    }
  });
}

module.exports = { startLocalServer, stopLocalServer };

