import { useState, useRef, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { filesAPI, extractionAPI, workspacesAPI } from '../utils/api'
import Card from '../components/Card'
import Button from '../components/Button'
import { FaTrash, FaEye, FaSearch, FaRedo, FaCheckSquare, FaSquare, FaFilter, FaCloudUploadAlt } from 'react-icons/fa'

const Upload = () => {
  const [dragActive, setDragActive] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadedFiles, setUploadedFiles] = useState([])
  const [workspaceId, setWorkspaceId] = useState(null)
  const [loadingWorkspace, setLoadingWorkspace] = useState(true)
  const [deletingId, setDeletingId] = useState(null)
  const [retryingId, setRetryingId] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all') // all, completed, processing, failed, uploaded
  const [dateRangeFilter, setDateRangeFilter] = useState('all') // all, today, week, month, year
  const [fileTypeFilter, setFileTypeFilter] = useState('all') // all, pdf, image, excel
  const [showFilters, setShowFilters] = useState(false)
  const [currentPage, setCurrentPage] = useState(1)
  const [selectedFiles, setSelectedFiles] = useState(new Set())
  const [isDeletingMultiple, setIsDeletingMultiple] = useState(false)
  const [estimatedTimes, setEstimatedTimes] = useState({}) // {fileId: {minutes, seconds}}
  const itemsPerPage = 10
  const fileInputRef = useRef(null)
  const navigate = useNavigate()
  const refreshIntervalRef = useRef(null)

  useEffect(() => {
    // Fetch user's default workspace
    const fetchWorkspace = async () => {
      try {
        const workspace = await workspacesAPI.getDefaultWorkspace()
        setWorkspaceId(workspace.id)
      } catch (error) {
        console.error('Failed to fetch workspace:', error)
        // Fallback to workspace ID 1 if API fails
        setWorkspaceId(1)
      } finally {
        setLoadingWorkspace(false)
      }
    }
    fetchWorkspace()
    
    // Load existing files
    loadFiles()
    
    // Set up auto-refresh for processing files
    refreshIntervalRef.current = setInterval(() => {
      loadFiles()
    }, 3000) // Refresh every 3 seconds
    
    return () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current)
      }
    }
  }, [workspaceId])

  const loadFiles = async () => {
    if (!workspaceId) return
    try {
      const files = await filesAPI.listFiles(workspaceId)
      // Sort by created_at descending (no limit - show all files)
      const sortedFiles = files
        .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
      setUploadedFiles(sortedFiles)
      
      // Fetch estimated times for processing files
      const processingFiles = sortedFiles.filter(f => f.status === 'processing')
      if (processingFiles.length > 0) {
        const timePromises = processingFiles.map(async (file) => {
          try {
            const estimate = await filesAPI.getEstimatedTime(file.id)
            return { fileId: file.id, estimate }
          } catch (error) {
            console.error(`Failed to get estimated time for file ${file.id}:`, error)
            return { fileId: file.id, estimate: null }
          }
        })
        
        const timeResults = await Promise.all(timePromises)
        const newEstimatedTimes = {}
        timeResults.forEach(({ fileId, estimate }) => {
          if (estimate && estimate.estimated_minutes_remaining !== null) {
            newEstimatedTimes[fileId] = estimate
          }
        })
        setEstimatedTimes(newEstimatedTimes)
      } else {
        // Clear estimates if no processing files
        setEstimatedTimes({})
      }
    } catch (error) {
      console.error('Failed to load files:', error)
    }
  }

  const handleDrag = (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFiles(e.dataTransfer.files)
    }
  }

  const handleFileInput = (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFiles(e.target.files)
    }
  }

  const handleFiles = async (files) => {
    const fileArray = Array.from(files)
    
    for (const file of fileArray) {
      await uploadFile(file)
    }
  }

  const uploadFile = async (file) => {
    if (!workspaceId) {
      alert('Workspace not loaded. Please wait...')
      return
    }
    
    try {
      setUploading(true)
      const uploadedFile = await filesAPI.upload(file, workspaceId)
      
      // Reload files to get updated list
      await loadFiles()
      
      // Automatically trigger extraction
      try {
        await extractionAPI.extract(uploadedFile.id)
      } catch (err) {
        console.error('Extraction trigger failed:', err)
      }
    } catch (error) {
      alert(`Upload failed: ${error.message}`)
    } finally {
      setUploading(false)
    }
  }

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
  }

  const documentTypeLabel = (docType) => {
    if (!docType) return null
    const labels = {
      individual_check: 'Single check',
      bank_statement_only: 'Bank statement',
      bank_statement_with_checks: 'Statement + checks',
      multi_check: 'Multiple checks',
    }
    return labels[docType] || docType
  }

  const fileTypeFilterLabel = (value) => {
    const labels = {
      single_check: 'Single check',
      multiple_checks: 'Multiple checks',
      bank_statement: 'Bank statement',
      statement_checks: 'Statement + checks',
    }
    return labels[value] || value
  }

  const formatDate = (dateString) => {
    if (!dateString) return ''
    const date = new Date(dateString)
    return date.toLocaleDateString('en-US', { 
      month: 'short', 
      day: 'numeric', 
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    })
  }

  const handleDelete = async (fileId, filename) => {
    if (!window.confirm(`Are you sure you want to delete "${filename}"? This action cannot be undone.`)) {
      return
    }

    try {
      setDeletingId(fileId)
      await filesAPI.deleteFile(fileId)
      // Reload files after deletion
      await loadFiles()
    } catch (err) {
      alert(`Failed to delete file: ${err.message}`)
    } finally {
      setDeletingId(null)
    }
  }

  const handleRetry = async (fileId, filename) => {
    if (!window.confirm(`Retry extraction for "${filename}"?`)) {
      return
    }

    try {
      setRetryingId(fileId)
      await extractionAPI.retryExtraction(fileId)
      // Reload files to show updated status
      await loadFiles()
    } catch (err) {
      alert(`Failed to retry extraction: ${err.message}`)
    } finally {
      setRetryingId(null)
    }
  }

  const handleSelectFile = (fileId) => {
    setSelectedFiles(prev => {
      const newSet = new Set(prev)
      if (newSet.has(fileId)) {
        newSet.delete(fileId)
      } else {
        newSet.add(fileId)
      }
      return newSet
    })
  }

  const handleSelectAll = () => {
    if (selectedFiles.size === paginatedFiles.length) {
      setSelectedFiles(new Set())
    } else {
      setSelectedFiles(new Set(paginatedFiles.map(f => f.id)))
    }
  }

  const handleDeleteMultiple = async () => {
    if (selectedFiles.size === 0) return
    
    const fileCount = selectedFiles.size
    if (!window.confirm(`Are you sure you want to delete ${fileCount} file(s)? This action cannot be undone.`)) {
      return
    }

    try {
      setIsDeletingMultiple(true)
      const deletePromises = Array.from(selectedFiles).map(fileId => 
        filesAPI.deleteFile(fileId).catch(err => {
          console.error(`Failed to delete file ${fileId}:`, err)
          return { error: true, fileId }
        })
      )
      
      await Promise.all(deletePromises)
      setSelectedFiles(new Set())
      await loadFiles()
    } catch (err) {
      alert(`Failed to delete some files: ${err.message}`)
    } finally {
      setIsDeletingMultiple(false)
    }
  }

  // Filter files based on search query and filters
  const filteredFiles = useMemo(() => {
    let filtered = uploadedFiles

    // Apply search query
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase()
      filtered = filtered.filter(file => {
        const docLabel = (file.document_type && documentTypeLabel(file.document_type)) || ''
        return (
          file.original_filename.toLowerCase().includes(query) ||
          file.file_type.toLowerCase().includes(query) ||
          file.status.toLowerCase().includes(query) ||
          (file.document_type && file.document_type.toLowerCase().includes(query)) ||
          docLabel.toLowerCase().includes(query)
        )
      })
    }

    // Apply status filter
    if (statusFilter !== 'all') {
      filtered = filtered.filter(file => file.status === statusFilter)
    }

    // Apply file type filter (by document_type: Single check, Multiple checks, Bank statement, Statement + checks)
    if (fileTypeFilter !== 'all') {
      const docTypeMap = {
        single_check: 'individual_check',
        multiple_checks: 'multi_check',
        bank_statement: 'bank_statement_only',
        statement_checks: 'bank_statement_with_checks',
      }
      const targetDocType = docTypeMap[fileTypeFilter]
      if (targetDocType) {
        filtered = filtered.filter(file => file.document_type === targetDocType)
      } else {
        filtered = filtered.filter(file => file.file_type.toLowerCase() === fileTypeFilter.toLowerCase())
      }
    }

    // Apply date range filter
    if (dateRangeFilter !== 'all') {
      const now = new Date()
      const filterDate = new Date()
      
      switch (dateRangeFilter) {
        case 'today':
          filterDate.setHours(0, 0, 0, 0)
          break
        case 'week':
          filterDate.setDate(now.getDate() - 7)
          break
        case 'month':
          filterDate.setMonth(now.getMonth() - 1)
          break
        case 'year':
          filterDate.setFullYear(now.getFullYear() - 1)
          break
        default:
          break
      }
      
      filtered = filtered.filter(file => {
        const fileDate = new Date(file.created_at)
        return fileDate >= filterDate
      })
    }

    return filtered
  }, [uploadedFiles, searchQuery, statusFilter, dateRangeFilter, fileTypeFilter])

  // Paginate filtered files
  const paginatedFiles = useMemo(() => {
    const startIndex = (currentPage - 1) * itemsPerPage
    const endIndex = startIndex + itemsPerPage
    return filteredFiles.slice(startIndex, endIndex)
  }, [filteredFiles, currentPage, itemsPerPage])

  const totalPages = Math.ceil(filteredFiles.length / itemsPerPage)

  // Reset to page 1 when filters change
  useEffect(() => {
    setCurrentPage(1)
  }, [searchQuery, statusFilter, dateRangeFilter, fileTypeFilter])

  if (loadingWorkspace) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">Upload</h1>

      {/* Compact upload strip */}
      <div
        className={`flex items-center gap-3 px-4 py-3 rounded-lg border-2 border-dashed transition-colors ${
          dragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300 bg-gray-50/50 hover:border-gray-400'
        }`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <FaCloudUploadAlt className="text-gray-500 text-xl flex-shrink-0" />
        <span className="text-sm text-gray-600">
          Drop files here or
        </span>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleFileInput}
          accept=".pdf,.jpg,.jpeg,.png,.xlsx,.xls"
          className="hidden"
        />
        <Button
          onClick={() => fileInputRef.current?.click()}
          variant="primary"
          disabled={uploading}
          className="text-sm px-4 py-1.5"
        >
          {uploading ? 'Uploading...' : 'Choose Files'}
        </Button>
        <span className="text-xs text-gray-400 ml-1">Only PDF files are supported</span>
      </div>

      {/* Uploaded Files List */}
      <Card>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Uploaded Files</h2>
              <p className="text-sm text-gray-500 mt-1">
                {filteredFiles.length} {filteredFiles.length === 1 ? 'file' : 'files'}
                {searchQuery && ` matching "${searchQuery}"`}
                {statusFilter !== 'all' && ` • Status: ${statusFilter}`}
                {dateRangeFilter !== 'all' && ` • ${dateRangeFilter.charAt(0).toUpperCase() + dateRangeFilter.slice(1)}`}
                {fileTypeFilter !== 'all' && ` • ${fileTypeFilterLabel(fileTypeFilter)}`}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowFilters(!showFilters)}
                className={`flex items-center gap-2 px-3 py-2 text-sm rounded-lg transition-colors ${
                  showFilters
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                }`}
              >
                <FaFilter />
                Filters
              </button>
              {selectedFiles.size > 0 && (
                <Button
                  onClick={handleDeleteMultiple}
                  disabled={isDeletingMultiple}
                  variant="secondary"
                  className="text-sm"
                >
                  {isDeletingMultiple ? 'Deleting...' : `Delete Selected (${selectedFiles.size})`}
                </Button>
              )}
            </div>
          </div>

          {/* Search Filter */}
          <div className="relative">
            <FaSearch className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 text-sm" />
            <input
              type="text"
              placeholder="Search files by name, type, or status..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* Advanced Filters */}
          {showFilters && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
              {/* Status Filter */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="all">All Statuses</option>
                  <option value="completed">Completed</option>
                  <option value="processing">Processing</option>
                  <option value="failed">Failed</option>
                  <option value="uploaded">Uploaded</option>
                </select>
              </div>

              {/* Date Range Filter */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Date Range</label>
                <select
                  value={dateRangeFilter}
                  onChange={(e) => setDateRangeFilter(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="all">All Time</option>
                  <option value="today">Today</option>
                  <option value="week">Last 7 Days</option>
                  <option value="month">Last 30 Days</option>
                  <option value="year">Last Year</option>
                </select>
              </div>

              {/* File Type Filter (by document type) */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Document Type</label>
                <select
                  value={fileTypeFilter}
                  onChange={(e) => setFileTypeFilter(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="all">All Types</option>
                  <option value="single_check">Single check</option>
                  <option value="multiple_checks">Multiple checks</option>
                  <option value="bank_statement">Bank statement</option>
                  <option value="statement_checks">Statement + checks</option>
                </select>
              </div>
            </div>
          )}

          {/* Files List - Table with aligned header and rows */}
          {paginatedFiles.length > 0 ? (
            <>
              {/* Table: same column widths for header and body */}
              <div className="border border-gray-200 rounded-lg overflow-hidden">
                {/* Header row - exact same grid as body rows */}
                <div
                  className="grid items-center gap-x-4 gap-y-0 px-4 py-2.5 bg-gray-100 border-b border-gray-200 text-xs font-semibold text-gray-600 uppercase tracking-wide"
                  style={{ gridTemplateColumns: 'auto minmax(0,1fr) 10rem 6rem 8rem 6.5rem 5rem' }}
                >
                  <div className="flex items-center justify-center gap-1.5">
                    <button
                      onClick={handleSelectAll}
                      className="text-gray-600 hover:text-gray-900"
                      title="Select all"
                    >
                      {selectedFiles.size === paginatedFiles.length ? (
                        <FaCheckSquare className="text-blue-600" />
                      ) : (
                        <FaSquare className="text-gray-400" />
                      )}
                    </button>
                    {selectedFiles.size > 0 && (
                      <span className="normal-case font-normal text-gray-500">({selectedFiles.size})</span>
                    )}
                  </div>
                  <span className="text-center">Filename</span>
                  <span className="text-center">Date</span>
                  <span className="text-center">Size</span>
                  <span className="text-center">Doc type</span>
                  <span className="text-center">Status</span>
                  <span className="text-center">Actions</span>
                </div>

                <div className="max-h-[600px] overflow-y-auto bg-white">
                  {paginatedFiles.map((file) => (
                    <div
                      key={file.id}
                      role={file.status === 'completed' ? 'button' : undefined}
                      tabIndex={file.status === 'completed' ? 0 : undefined}
                      onClick={(e) => {
                        if (file.status === 'completed' && !e.target.closest('button')) {
                          navigate(`/extracted/${file.id}`)
                        }
                      }}
                      onKeyDown={(e) => {
                        if (file.status === 'completed' && (e.key === 'Enter' || e.key === ' ') && !e.target.closest('button')) {
                          e.preventDefault()
                          navigate(`/extracted/${file.id}`)
                        }
                      }}
                      className={`grid items-center gap-x-4 gap-y-0 px-4 py-2 border-b border-gray-100 last:border-b-0 transition-colors ${
                        selectedFiles.has(file.id)
                          ? 'bg-blue-50'
                          : 'hover:bg-gray-50'
                      } ${file.status === 'completed' ? 'cursor-pointer' : ''}`}
                      style={{ gridTemplateColumns: 'auto minmax(0,1fr) 10rem 6rem 8rem 6.5rem 5rem' }}
                    >
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); handleSelectFile(file.id) }}
                        className="flex-shrink-0 w-5"
                      >
                        {selectedFiles.has(file.id) ? (
                          <FaCheckSquare className="text-blue-600" />
                        ) : (
                          <FaSquare className="text-gray-400 hover:text-gray-600" />
                        )}
                      </button>
                      <p className="text-sm font-medium text-gray-900 truncate min-w-0" title={file.original_filename}>
                        {file.original_filename}
                      </p>
                      <span className="text-xs text-gray-600 whitespace-nowrap text-right">{formatDate(file.created_at)}</span>
                      <span className="text-xs text-gray-600 whitespace-nowrap text-right">
                        {formatFileSize(file.file_size)}
                      </span>
                      <div className="min-w-0">
                        {file.document_type ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-800 whitespace-nowrap">
                            {documentTypeLabel(file.document_type)}
                          </span>
                        ) : (
                          <span className="text-xs text-gray-400">—</span>
                        )}
                      </div>
                      <div className="min-w-0">
                        <span
                          className={`inline-block px-2 py-0.5 text-xs font-semibold rounded-full whitespace-nowrap truncate max-w-full ${
                            file.status === 'completed'
                              ? 'bg-green-100 text-green-800'
                              : file.status === 'processing'
                              ? 'bg-yellow-100 text-yellow-800'
                              : file.status === 'failed'
                              ? 'bg-red-100 text-red-800'
                              : 'bg-gray-100 text-gray-800'
                          }`}
                          title={file.status === 'failed' && file.error_message ? file.error_message : undefined}
                        >
                          {file.status}
                          {file.status === 'processing' && estimatedTimes[file.id] && (
                            <span className="font-normal text-gray-600"> ~{estimatedTimes[file.id].estimated_minutes_remaining}m</span>
                          )}
                        </span>
                      </div>
                      <div className="flex items-center justify-end gap-0.5" onClick={(e) => e.stopPropagation()}>
                        {file.status === 'completed' && (
                          <button
                            type="button"
                            onClick={() => navigate(`/extracted/${file.id}`)}
                            className="text-blue-600 hover:text-blue-900 p-1 rounded hover:bg-blue-100"
                            title="View extraction results"
                          >
                            <FaEye className="text-sm" />
                          </button>
                        )}
                        {file.status === 'failed' && (
                          <button
                            type="button"
                            onClick={() => handleRetry(file.id, file.original_filename)}
                            disabled={retryingId === file.id}
                            className="text-green-600 hover:text-green-900 disabled:opacity-50 p-1 rounded hover:bg-green-100"
                            title={retryingId === file.id ? 'Retrying...' : 'Retry extraction'}
                          >
                            <FaRedo className={`text-sm ${retryingId === file.id ? 'animate-spin' : ''}`} />
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => handleDelete(file.id, file.original_filename)}
                          disabled={deletingId === file.id}
                          className="text-red-600 hover:text-red-900 disabled:opacity-50 p-1 rounded hover:bg-red-100"
                          title={deletingId === file.id ? 'Deleting...' : 'Delete file'}
                        >
                          <FaTrash className="text-sm" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between border-t border-gray-200 pt-4">
                  <div className="text-sm text-gray-700">
                    Showing {(currentPage - 1) * itemsPerPage + 1} to{' '}
                    {Math.min(currentPage * itemsPerPage, filteredFiles.length)} of{' '}
                    {filteredFiles.length} files
                  </div>
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                      disabled={currentPage === 1}
                      className="px-3 py-1 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Previous
                    </button>
                    <div className="flex items-center space-x-1">
                      {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                        let pageNum
                        if (totalPages <= 5) {
                          pageNum = i + 1
                        } else if (currentPage <= 3) {
                          pageNum = i + 1
                        } else if (currentPage >= totalPages - 2) {
                          pageNum = totalPages - 4 + i
                        } else {
                          pageNum = currentPage - 2 + i
                        }
                        return (
                          <button
                            key={pageNum}
                            onClick={() => setCurrentPage(pageNum)}
                            className={`px-3 py-1 text-sm rounded-lg ${
                              currentPage === pageNum
                                ? 'bg-blue-600 text-white'
                                : 'border border-gray-300 hover:bg-gray-50'
                            }`}
                          >
                            {pageNum}
                          </button>
                        )
                      })}
                    </div>
                    <button
                      onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                      disabled={currentPage === totalPages}
                      className="px-3 py-1 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-12 text-gray-500">
              {searchQuery ? (
                <p>No files found matching "{searchQuery}"</p>
              ) : (
                <p>No files uploaded yet. Upload your first file above.</p>
              )}
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}

export default Upload

