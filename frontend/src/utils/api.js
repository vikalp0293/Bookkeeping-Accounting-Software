// Import storage utility
import storage from './storage.js'
import { isElectron } from './electron-api.js'

// Export API_BASE_URL so it can be imported elsewhere
// In development (web), use relative URL to leverage Vite proxy
// In Electron, get from settings; otherwise use env variable
let API_BASE_URL = import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? '/api/v1' : 'http://localhost:5208/api/v1')

// Initialize API_BASE_URL from Electron settings if available (async, don't block)
if (isElectron() && typeof window !== 'undefined' && window.electronAPI) {
  window.electronAPI.getSettings().then(settings => {
    if (settings?.backendUrl) {
      API_BASE_URL = `${settings.backendUrl}/api/v1`
    }
  }).catch(() => {
    // Fallback to default
  })
}

// Export API_BASE_URL for use in other components
export { API_BASE_URL }

// Get auth token from storage (localStorage or electron-store)
// Works synchronously for web, async for Electron
const getAuthToken = () => {
  if (isElectron()) {
    // For Electron, use async version
    return storage.getItemAsync('access_token')
  } else {
    // For web, use synchronous version
    return Promise.resolve(storage.getItem('access_token'))
  }
}

// Base fetch wrapper
const apiRequest = async (endpoint, options = {}) => {
  const token = await getAuthToken() // Works for both web and Electron
  const url = `${API_BASE_URL}${endpoint}`
  
  const config = {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token && { Authorization: `Bearer ${token}` }),
      ...options.headers,
    },
  }
  
  try {
    const response = await fetch(url, config)
    
    // Handle 204 No Content responses (no body)
    if (response.status === 204) {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      return { ok: true, status: 204 }
    }
    
    // Handle non-JSON responses
    const contentType = response.headers.get('content-type')
    if (!contentType || !contentType.includes('application/json')) {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      return { ok: response.ok, status: response.status }
    }
    
    // Check if response has content before parsing JSON
    const text = await response.text()
    if (!text) {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      return { ok: response.ok, status: response.status }
    }
    
    const data = JSON.parse(text)
    
    if (!response.ok) {
      // If 401 and we have a refresh token, try to refresh
      if (response.status === 401 && isElectron()) {
        const refreshToken = await storage.getItemAsync('refresh_token')
        if (refreshToken) {
          try {
            // Try to refresh token
            const refreshResponse = await fetch(`${API_BASE_URL}/auth/refresh`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ refresh_token: refreshToken }),
            })
            
            if (refreshResponse.ok) {
              const refreshData = await refreshResponse.json()
              // Save new access token
              await storage.setItemAsync('access_token', refreshData.access_token)
              
              // Retry original request with new token
              const newToken = refreshData.access_token
              const retryConfig = {
                ...options,
                headers: {
                  'Content-Type': 'application/json',
                  ...(newToken && { Authorization: `Bearer ${newToken}` }),
                  ...options.headers,
                },
              }
              const retryResponse = await fetch(url, retryConfig)
              const retryText = await retryResponse.text()
              if (!retryText) {
                return { ok: retryResponse.ok, status: retryResponse.status }
              }
              const retryData = JSON.parse(retryText)
              if (!retryResponse.ok) {
                throw new Error(retryData.detail || 'An error occurred')
              }
              return retryData
            }
          } catch (refreshError) {
            // Refresh failed, throw original error
            console.error('Token refresh failed:', refreshError)
          }
        }
      }
      
      const msg = (typeof data.detail === 'object' && data.detail?.message)
        ? data.detail.message
        : (data.detail || 'An error occurred')
      const err = new Error(msg)
      err.detail = data.detail
      throw err
    }
    
    return data
  } catch (error) {
    console.error('API request failed:', error)
    throw error
  }
}

// Auth API
export const authAPI = {
  login: async (email, password) => {
    return apiRequest('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
  },
  
  refreshToken: async (refresh_token) => {
    return apiRequest('/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token }),
    })
  },
  
  getCurrentUser: async () => {
    return apiRequest('/auth/me')
  },
}

// Files API
export const filesAPI = {
  upload: async (file, workspaceId) => {
    const token = await getAuthToken() // Works for both web and Electron
    const formData = new FormData()
    formData.append('file', file)
    formData.append('workspace_id', String(workspaceId))
    
    const response = await fetch(`${API_BASE_URL}/files/upload`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: formData,
    })
    
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Upload failed')
    }
    
    return response.json()
  },
  
  getFile: async (fileId) => {
    return apiRequest(`/files/${fileId}`)
  },
  
  listFiles: async (workspaceId = null) => {
    const params = workspaceId ? `?workspace_id=${workspaceId}` : ''
    return apiRequest(`/files/list/all${params}`)
  },
  
  deleteFile: async (fileId) => {
    return apiRequest(`/files/${fileId}`, {
      method: 'DELETE',
    })
  },

  getEstimatedTime: async (fileId) => {
    return apiRequest(`/files/${fileId}/estimated-time`)
  },
}

// Extraction API
export const extractionAPI = {
  extract: async (fileId) => {
    return apiRequest(`/extract/${fileId}`, {
      method: 'POST',
    })
  },
  
  getExtraction: async (fileId) => {
    return apiRequest(`/extract/${fileId}`)
  },
  
  cancelExtraction: async (fileId) => {
    return apiRequest(`/extract/${fileId}/cancel`, {
      method: 'POST',
    })
  },
  
  retryExtraction: async (fileId) => {
    return apiRequest(`/extract/${fileId}/retry`, {
      method: 'POST',
    })
  },
}

// Dashboard API
export const dashboardAPI = {
  getStats: async (workspaceId = null) => {
    const params = workspaceId ? `?workspace_id=${workspaceId}` : ''
    return apiRequest(`/stats/summary${params}`)
  },
}

// Workspaces API
export const workspacesAPI = {
  getWorkspaces: async () => {
    return apiRequest('/workspaces')
  },
  
  getDefaultWorkspace: async () => {
    return apiRequest('/workspaces/default')
  },
  
  updateWorkspace: async (workspaceId, data) => {
    return apiRequest(`/workspaces/${workspaceId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  },
}

// User Management API (RBAC)
export const userManagementAPI = {
  listUsers: async (params = {}) => {
    const qs = new URLSearchParams()
    if (params.role) qs.set('role', params.role)
    if (params.workspace_id != null) qs.set('workspace_id', String(params.workspace_id))
    const suffix = qs.toString() ? `?${qs.toString()}` : ''
    return apiRequest(`/users${suffix}`)
  },

  createAdmin: async ({ email, password, full_name, workspace_name }) => {
    return apiRequest('/users/admin', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name, workspace_name }),
    })
  },

  createWorkspaceUser: async ({ email, password, full_name, role }) => {
    return apiRequest('/users/workspace-user', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name, role }),
    })
  },
}


// Review Queue API
export const reviewQueueAPI = {
  getQueue: async (workspaceId = null, status = null, priority = null, limit = 100) => {
    const params = new URLSearchParams()
    if (workspaceId) params.append('workspace_id', workspaceId)
    if (status) params.append('status', status)
    if (priority) params.append('priority', priority)
    if (limit) params.append('limit', limit)
    return apiRequest(`/review-queue?${params.toString()}`)
  },
  
  getStats: async (workspaceId = null) => {
    const params = workspaceId ? `?workspace_id=${workspaceId}` : ''
    return apiRequest(`/review-queue/stats${params}`)
  },
  
  assignReview: async (reviewId) => {
    return apiRequest(`/review-queue/${reviewId}/assign`, {
      method: 'POST',
    })
  },
  
  updateReview: async (reviewId, status, notes = null) => {
    return apiRequest(`/review-queue/${reviewId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status, notes }),
    })
  },
}

// Payees API
export const payeesAPI = {
  getPayees: async (workspaceId, limit = 50) => {
    return apiRequest(`/payees?workspace_id=${workspaceId}&limit=${limit}`)
  },
  
  getSuggestions: async (workspaceId, limit = 10) => {
    return apiRequest(`/payees/suggestions?workspace_id=${workspaceId}&limit=${limit}`)
  },
  
  getRecent: async (workspaceId, limit = 10) => {
    return apiRequest(`/payees/recent?workspace_id=${workspaceId}&limit=${limit}`)
  },
  
  createPayee: async (workspaceId, payeeName, autoMatch = true) => {
    return apiRequest(`/payees?workspace_id=${workspaceId}`, {
      method: 'POST',
      body: JSON.stringify({ payee_name: payeeName, auto_match: autoMatch }),
    })
  },
  
  correctPayee: async (workspaceId, payeeId, originalPayee, correctedPayee, fileId = null, transactionId = null) => {
    return apiRequest(`/payees/correct?workspace_id=${workspaceId}&payee_id=${payeeId}`, {
      method: 'POST',
      body: JSON.stringify({
        original_payee: originalPayee,
        corrected_payee: correctedPayee,
        file_id: fileId,
        transaction_id: transactionId,
      }),
    })
  },
  
  matchPayee: async (workspaceId, payeeName, threshold = 85) => {
    return apiRequest(`/payees/match?workspace_id=${workspaceId}&payee_name=${encodeURIComponent(payeeName)}&threshold=${threshold}`)
  },
}

// Vendors & Categories API
export const vendorsAPI = {
  getVendors: async (limit = 100) => {
    return apiRequest(`/vendors/vendors?limit=${limit}`)
  },
  
  getCategories: async (limit = 100) => {
    return apiRequest(`/vendors/categories?limit=${limit}`)
  },
  
  createVendor: async (name, categoryId = null, subcategory = null, commonPayeePatterns = null) => {
    return apiRequest(`/vendors/vendors`, {
      method: 'POST',
      body: JSON.stringify({
        name,
        category_id: categoryId,
        subcategory,
        common_payee_patterns: commonPayeePatterns
      }),
    })
  },
  
  createCategory: async (name, description = null) => {
    return apiRequest(`/vendors/categories`, {
      method: 'POST',
      body: JSON.stringify({
        name,
        description
      }),
    })
  },
  
  suggestVendorCategory: async (payeeName, threshold = 80) => {
    return apiRequest(`/vendors/suggest?payee_name=${encodeURIComponent(payeeName)}&threshold=${threshold}`)
  },
}

// QuickBooks Queue API
export const qbQueueAPI = {
  checkUnmappedPayees: async (workspaceId, { fileIds = null, transactionList = null } = {}) => {
    return apiRequest(`/qb-queue/check-unmapped-payees?workspace_id=${workspaceId}`, {
      method: 'POST',
      body: JSON.stringify({
        file_ids: fileIds,
        transaction_list: transactionList
      }),
    })
  },

  queueTransaction: async (workspaceId, fileId, transactionData, transactionIndex = null, transactionId = null, companyFile = null) => {
    const body = {
      file_id: fileId,
      transaction_data: transactionData,
      transaction_index: transactionIndex,
      transaction_id: transactionId
    }
    if (companyFile != null && companyFile !== '') body.company_file = companyFile
    return apiRequest(`/qb-queue/queue?workspace_id=${workspaceId}`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },
  
  approveTransactions: async (workspaceId, queueIds) => {
    return apiRequest(`/qb-queue/approve?workspace_id=${workspaceId}`, {
      method: 'POST',
      body: JSON.stringify({ queue_ids: queueIds }),
    })
  },
  
  rejectTransaction: async (workspaceId, queueId) => {
    return apiRequest(`/qb-queue/reject/${queueId}?workspace_id=${workspaceId}`, {
      method: 'DELETE',
    })
  },
  
  listQueue: async (workspaceId, status = null, limit = 100) => {
    const params = new URLSearchParams()
    params.append('workspace_id', workspaceId)
    if (status) params.append('status', status)
    if (limit) params.append('limit', limit)
    return apiRequest(`/qb-queue/list?${params.toString()}`)
  },
  
  getQueueStats: async (workspaceId) => {
    return apiRequest(`/qb-queue/stats?workspace_id=${workspaceId}`)
  },
  
  exportToIIF: async (workspaceId, fileId = null, limit = 1000) => {
    // Fetch IIF file with authentication and trigger download
    // Exports all extracted transactions from the workspace
    try {
      const token = await getAuthToken()
      const params = new URLSearchParams()
      params.append('limit', limit.toString())
      // Add file_id parameter if provided (to export only from specific file)
      if (fileId) {
        params.append('file_id', fileId.toString())
      }
      const url = `${API_BASE_URL}/export/quickbooks/queued/${workspaceId}?${params.toString()}`
      
      const response = await fetch(url, {
        headers: {
          ...(token && { Authorization: `Bearer ${token}` }),
        },
      })
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }))
        throw new Error(errorData.detail || `Export failed: ${response.statusText}`)
      }
      
      // Get filename from Content-Disposition header or use default
      const contentDisposition = response.headers.get('Content-Disposition')
      let filename = `quickbooks_export_${workspaceId}_${new Date().toISOString().split('T')[0]}.iif`
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename="?(.+)"?/i)
        if (filenameMatch) {
          filename = filenameMatch[1]
        }
      }
      
      // Create blob and trigger download
      const blob = await response.blob()
      const blobUrl = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = blobUrl
      link.download = filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(blobUrl)
    } catch (error) {
      console.error('Failed to export IIF file:', error)
      throw error
    }
  },
}

// Activity Logs API
export const activityLogsAPI = {
  getLogs: async (params = {}) => {
    const queryParams = new URLSearchParams()
    if (params.workspaceId) queryParams.append('workspace_id', params.workspaceId)
    if (params.actionType) queryParams.append('action_type', params.actionType)
    if (params.resourceType) queryParams.append('resource_type', params.resourceType)
    if (params.startDate) queryParams.append('start_date', params.startDate)
    if (params.endDate) queryParams.append('end_date', params.endDate)
    if (params.limit) queryParams.append('limit', params.limit)
    if (params.offset) queryParams.append('offset', params.offset)
    const query = queryParams.toString()
    return apiRequest(`/activity-logs${query ? `?${query}` : ''}`)
  },

  getStats: async (workspaceId = null, days = 30) => {
    const params = new URLSearchParams()
    if (workspaceId) params.append('workspace_id', workspaceId)
    params.append('days', days)
    return apiRequest(`/activity-logs/stats?${params.toString()}`)
  },
}

// OCR Logs API
export const ocrLogsAPI = {
  getOCRLogs: async (lines = 500, level = null, fileId = null) => {
    const params = new URLSearchParams()
    params.append('lines', lines)
    if (level) params.append('level', level)
    if (fileId) params.append('file_id', fileId)
    return apiRequest(`/logs/ocr?${params.toString()}`)
  },

  getExtractionLogs: async (lines = 500, level = null, fileId = null) => {
    const params = new URLSearchParams()
    params.append('lines', lines)
    if (level) params.append('level', level)
    if (fileId) params.append('file_id', fileId)
    return apiRequest(`/logs/extraction?${params.toString()}`)
  },

  getLogInfo: async () => {
    return apiRequest('/logs/info')
  },
}

// Payee Management API (extend existing payee API)
export const payeeManagementAPI = {
  ...payeesAPI, // Include existing payee API methods
  
  updatePayee: async (workspaceId, payeeId, data) => {
    return apiRequest(`/payees/${payeeId}?workspace_id=${workspaceId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    })
  },

  deletePayee: async (workspaceId, payeeId) => {
    return apiRequest(`/payees/${payeeId}?workspace_id=${workspaceId}`, {
      method: 'DELETE',
    })
  },

  mergePayees: async (workspaceId, sourcePayeeId, targetPayeeId) => {
    return apiRequest(`/payees/merge?workspace_id=${workspaceId}`, {
      method: 'POST',
      body: JSON.stringify({
        source_payee_id: sourcePayeeId,
        target_payee_id: targetPayeeId,
      }),
    })
  },

  getPayeeCorrections: async (workspaceId, payeeId = null) => {
    const params = new URLSearchParams()
    params.append('workspace_id', workspaceId)
    if (payeeId) params.append('payee_id', payeeId)
    return apiRequest(`/payees/corrections?${params.toString()}`)
  },
}


