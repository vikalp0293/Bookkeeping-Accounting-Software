/**
 * Directory Monitor Service
 * Monitors a directory for new files and uploads them to the backend
 */

const chokidar = require('chokidar');
const path = require('path');
const fs = require('fs').promises;
const axios = require('axios');
const log = require('./logger').log;
const Store = require('electron-store');

// File extensions to monitor
const SUPPORTED_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.tif'];

// Store for tracking processed files
const processedFilesStore = new Store({
  name: 'processed-files',
  defaults: {
    files: [] // Array of { path, hash, uploadedAt, status }
  }
});

// Store for upload queue (persists across app restarts)
const uploadQueueStore = new Store({
  name: 'upload-queue',
  defaults: {
    queue: [] // Array of { path, attempts, lastAttempt }
  }
});

class DirectoryMonitor {
  constructor() {
    this.watcher = null;
    this.monitoredPath = null;
    this.isMonitoring = false;
    this.backendUrl = null;
    this.authToken = null;
    this.workspaceId = null;
    this.uploadQueue = [];
    this.isUploading = false;
    this.retryAttempts = 3;
    this.retryDelay = 5000; // 5 seconds
    this.isOnline = true;
    
    // Load persisted queue on startup
    this.loadPersistedQueue();
    
    // Set up online/offline detection
    this.setupNetworkDetection();
  }

  /**
   * Initialize the monitor with settings
   */
  initialize(settings) {
    this.backendUrl = settings.backendUrl || 'https://dev-sync-api.kylientlabs.com';
    this.authToken = settings.authToken || null;
    this.workspaceId = settings.workspaceId || null;
    log.info('Directory monitor initialized', {
      backendUrl: this.backendUrl,
      hasAuthToken: !!this.authToken,
      workspaceId: this.workspaceId
    });
  }

  /**
   * Start monitoring a directory
   */
  async startMonitoring(directoryPath) {
    if (this.isMonitoring) {
      log.warn('Monitor is already running');
      return { success: false, error: 'Monitor is already running' };
    }

    if (!directoryPath || !await this.directoryExists(directoryPath)) {
      log.error('Invalid directory path:', directoryPath);
      return { success: false, error: 'Invalid directory path' };
    }

    try {
      this.monitoredPath = directoryPath;
      
      // Create watcher with options
      this.watcher = chokidar.watch(directoryPath, {
        ignored: /(^|[\/\\])\../, // Ignore dotfiles
        persistent: true,
        ignoreInitial: false, // Process existing files
        awaitWriteFinish: {
          stabilityThreshold: 2000, // Wait 2 seconds after file stops changing
          pollInterval: 100 // Check every 100ms
        }
      });

      // Set up event handlers
      this.watcher
        .on('add', (filePath) => this.handleFileAdded(filePath))
        .on('change', (filePath) => this.handleFileChanged(filePath))
        .on('error', (error) => this.handleError(error))
        .on('ready', () => {
          log.info('Directory monitor ready:', directoryPath);
          this.isMonitoring = true;
        });

      log.info('Started monitoring directory:', directoryPath);
      return { success: true };
    } catch (error) {
      log.error('Failed to start monitoring:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Stop monitoring
   */
  async stopMonitoring() {
    if (!this.isMonitoring) {
      return { success: true };
    }

    try {
      if (this.watcher) {
        await this.watcher.close();
        this.watcher = null;
      }
      this.isMonitoring = false;
      this.monitoredPath = null;
      log.info('Stopped monitoring directory');
      return { success: true };
    } catch (error) {
      log.error('Error stopping monitor:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Handle new file added
   */
  async handleFileAdded(filePath) {
    log.info('File added:', filePath);
    
    if (!this.isSupportedFile(filePath)) {
      log.debug('File not supported, skipping:', filePath);
      return;
    }

    // Check if file was already processed
    if (await this.isFileProcessed(filePath)) {
      log.debug('File already processed, skipping:', filePath);
      return;
    }

    // Wait a bit to ensure file is fully written
    await this.delay(1000);

    // Add to upload queue
    await this.queueFileForUpload(filePath);
  }

  /**
   * Handle file changed
   */
  async handleFileChanged(filePath) {
    log.info('File changed:', filePath);
    
    if (!this.isSupportedFile(filePath)) {
      return;
    }

    // If file was previously processed, mark it as needing re-processing
    await this.markFileAsUnprocessed(filePath);
    await this.queueFileForUpload(filePath);
  }

  /**
   * Check if file is supported
   */
  isSupportedFile(filePath) {
    const ext = path.extname(filePath).toLowerCase();
    return SUPPORTED_EXTENSIONS.includes(ext);
  }

  /**
   * Check if directory exists
   */
  async directoryExists(dirPath) {
    try {
      const stats = await fs.stat(dirPath);
      return stats.isDirectory();
    } catch {
      return false;
    }
  }

  /**
   * Check if file was already processed
   */
  async isFileProcessed(filePath) {
    const processedFiles = processedFilesStore.get('files', []);
    const normalizedPath = path.normalize(filePath);
    
    return processedFiles.some(file => 
      path.normalize(file.path) === normalizedPath && 
      file.status === 'uploaded'
    );
  }

  /**
   * Mark file as processed
   */
  async markFileAsProcessed(filePath, fileId, status = 'uploaded') {
    const processedFiles = processedFilesStore.get('files', []);
    const normalizedPath = path.normalize(filePath);
    
    // Remove existing entry if any
    const filtered = processedFiles.filter(f => path.normalize(f.path) !== normalizedPath);
    
    // Add new entry
    filtered.push({
      path: normalizedPath,
      fileId: fileId,
      status: status,
      uploadedAt: new Date().toISOString()
    });
    
    processedFilesStore.set('files', filtered);
    log.info('Marked file as processed:', filePath, status);
  }

  /**
   * Mark file as unprocessed (for re-upload)
   */
  async markFileAsUnprocessed(filePath) {
    const processedFiles = processedFilesStore.get('files', []);
    const normalizedPath = path.normalize(filePath);
    
    const filtered = processedFiles.filter(f => path.normalize(f.path) !== normalizedPath);
    processedFilesStore.set('files', filtered);
  }

  /**
   * Load persisted queue from storage
   */
  loadPersistedQueue() {
    try {
      const persistedQueue = uploadQueueStore.get('queue', []);
      this.uploadQueue = persistedQueue;
      log.info(`Loaded ${persistedQueue.length} files from persisted queue`);
    } catch (error) {
      log.error('Failed to load persisted queue:', error);
      this.uploadQueue = [];
    }
  }

  /**
   * Save queue to persistent storage
   */
  savePersistedQueue() {
    try {
      uploadQueueStore.set('queue', this.uploadQueue);
    } catch (error) {
      log.error('Failed to save persisted queue:', error);
    }
  }

  /**
   * Setup network detection
   */
  setupNetworkDetection() {
    // Check network status periodically
    setInterval(async () => {
      const wasOffline = !this.isOnline;
      this.isOnline = await this.checkNetworkStatus();
      
      if (wasOffline && this.isOnline) {
        log.info('Network connection restored, processing queue...');
        if (this.uploadQueue.length > 0 && !this.isUploading) {
          this.processUploadQueue();
        }
      } else if (!wasOffline && !this.isOnline) {
        log.warn('Network connection lost');
      }
    }, 10000); // Check every 10 seconds
  }

  /**
   * Check network status
   */
  async checkNetworkStatus() {
    if (!this.backendUrl) return false;
    
    try {
      // Try a simple GET request to the backend root or a known endpoint
      const response = await axios.get(`${this.backendUrl}/api/v1/dashboard/stats`, {
        timeout: 5000,
        validateStatus: (status) => status < 500 // Accept 4xx as "online" (server responded)
      });
      return true;
    } catch (error) {
      // Network error or timeout means offline
      if (error.code === 'ECONNREFUSED' || error.code === 'ETIMEDOUT' || error.message.includes('timeout')) {
        return false;
      }
      // Other errors might mean server is online but endpoint doesn't exist
      // In that case, we consider it online (server responded)
      return error.response !== undefined;
    }
  }

  /**
   * Queue file for upload
   */
  async queueFileForUpload(filePath) {
    // Check if already in queue
    if (this.uploadQueue.some(item => item.path === filePath)) {
      log.debug('File already in queue:', filePath);
      return;
    }

    this.uploadQueue.push({
      path: filePath,
      attempts: 0,
      lastAttempt: null
    });

    // Persist queue
    this.savePersistedQueue();

    log.info('Queued file for upload:', filePath);
    
    // Start processing queue if not already processing and online
    if (!this.isUploading && this.isOnline) {
      this.processUploadQueue();
    } else if (!this.isOnline) {
      log.info('Offline - file queued for later upload');
    }
  }

  /**
   * Process upload queue
   */
  async processUploadQueue() {
    if (this.isUploading || this.uploadQueue.length === 0) {
      return;
    }

    // Don't process if offline
    if (!this.isOnline) {
      log.info('Offline - skipping queue processing');
      return;
    }

    this.isUploading = true;

    while (this.uploadQueue.length > 0 && this.isOnline) {
      const fileItem = this.uploadQueue[0]; // Peek at first item
      
      try {
        await this.uploadFile(fileItem.path);
        // Remove from queue on success
        this.uploadQueue.shift();
        this.savePersistedQueue();
      } catch (error) {
        log.error('Upload failed:', fileItem.path, error.message);
        
        // Check if it's a network error
        const isNetworkError = error.message.includes('Network error') || 
                               error.message.includes('No response from server') ||
                               !error.response;
        
        if (isNetworkError) {
          // Network error - mark as offline and stop processing
          this.isOnline = false;
          log.warn('Network error detected, stopping queue processing');
          break;
        }
        
        // Retry logic for non-network errors
        fileItem.attempts++;
        fileItem.lastAttempt = new Date().toISOString();
        
        if (fileItem.attempts < this.retryAttempts) {
          log.info(`Retrying upload (attempt ${fileItem.attempts + 1}/${this.retryAttempts}):`, fileItem.path);
          // Move to end of queue with delay
          this.uploadQueue.shift();
          this.uploadQueue.push(fileItem);
          this.savePersistedQueue();
          
          // Wait before retrying
          await this.delay(this.retryDelay);
        } else {
          log.error('Max retry attempts reached for:', fileItem.path);
          this.uploadQueue.shift();
          this.savePersistedQueue();
          await this.markFileAsProcessed(fileItem.path, null, 'failed');
        }
      }
    }

    this.isUploading = false;
    
    // If queue still has items and we're online, schedule next batch
    if (this.uploadQueue.length > 0 && this.isOnline) {
      setTimeout(() => {
        if (!this.isUploading) {
          this.processUploadQueue();
        }
      }, this.retryDelay);
    }
  }

  /**
   * Upload file to backend
   */
  async uploadFile(filePath) {
    if (!this.authToken) {
      throw new Error('No authentication token available');
    }

    if (!this.workspaceId) {
      throw new Error('No workspace ID available');
    }

    log.info('Uploading file:', filePath);

    try {
      // Read file
      const fileBuffer = await fs.readFile(filePath);
      const fileName = path.basename(filePath);
      const fileStats = await fs.stat(filePath);

      // Create form data
      const FormData = require('form-data');
      const formData = new FormData();
      formData.append('file', fileBuffer, {
        filename: fileName,
        contentType: this.getContentType(filePath)
      });
      formData.append('workspace_id', this.workspaceId.toString());

      // Upload to backend
      const response = await axios.post(
        `${this.backendUrl}/api/v1/files/upload`,
        formData,
        {
          headers: {
            'Authorization': `Bearer ${this.authToken}`,
            ...formData.getHeaders()
          },
          maxContentLength: Infinity,
          maxBodyLength: Infinity,
          timeout: 300000 // 5 minutes
        }
      );

      if (response.data && response.data.id) {
        log.info('File uploaded successfully:', filePath, 'File ID:', response.data.id);
        await this.markFileAsProcessed(filePath, response.data.id, 'uploaded');
        return response.data;
      } else {
        throw new Error('Invalid response from server');
      }
    } catch (error) {
      if (error.response) {
        // Server responded with error
        log.error('Upload error response:', error.response.status, error.response.data);
        throw new Error(`Upload failed: ${error.response.status} - ${JSON.stringify(error.response.data)}`);
      } else if (error.request) {
        // Request made but no response (offline)
        log.warn('No response from server (offline?):', filePath);
        throw new Error('Network error: No response from server');
      } else {
        // Other error
        log.error('Upload error:', error.message);
        throw error;
      }
    }
  }

  /**
   * Get content type for file
   */
  getContentType(filePath) {
    const ext = path.extname(filePath).toLowerCase();
    const contentTypes = {
      '.pdf': 'application/pdf',
      '.jpg': 'image/jpeg',
      '.jpeg': 'image/jpeg',
      '.png': 'image/png',
      '.tiff': 'image/tiff',
      '.tif': 'image/tiff'
    };
    return contentTypes[ext] || 'application/octet-stream';
  }

  /**
   * Handle errors
   */
  handleError(error) {
    log.error('Directory monitor error:', error);
  }

  /**
   * Get monitoring status
   */
  getStatus() {
    return {
      isMonitoring: this.isMonitoring,
      monitoredPath: this.monitoredPath,
      queueLength: this.uploadQueue.length,
      isUploading: this.isUploading,
      isOnline: this.isOnline
    };
  }

  /**
   * Clear upload queue
   */
  clearUploadQueue() {
    this.uploadQueue = [];
    this.savePersistedQueue();
    log.info('Upload queue cleared');
  }

  /**
   * Clear processed files history
   */
  clearProcessedFiles() {
    processedFilesStore.set('files', []);
    log.info('Cleared processed files history');
  }

  /**
   * Utility: Delay
   */
  delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

// Singleton instance
let monitorInstance = null;

function getMonitor() {
  if (!monitorInstance) {
    monitorInstance = new DirectoryMonitor();
  }
  return monitorInstance;
}

module.exports = { getMonitor };

