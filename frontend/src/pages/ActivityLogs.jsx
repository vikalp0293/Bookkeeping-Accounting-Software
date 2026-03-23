import { useState, useEffect } from 'react'
import { activityLogsAPI, workspacesAPI } from '../utils/api'
import Card from '../components/Card'
import { FaFilter, FaChartBar } from 'react-icons/fa'

const ActivityLogs = () => {
  const [logs, setLogs] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [workspaceId, setWorkspaceId] = useState(null)
  const [filters, setFilters] = useState({
    actionType: '',
    resourceType: '',
    startDate: '',
    endDate: '',
    limit: 100,
  })
  const [showFilters, setShowFilters] = useState(false)

  useEffect(() => {
    loadWorkspace()
  }, [])

  useEffect(() => {
    // Load logs even without workspaceId (login actions don't have workspace)
    loadLogs()
    if (workspaceId) {
      loadStats()
    }
  }, [workspaceId, filters])

  const loadWorkspace = async () => {
    try {
      const workspace = await workspacesAPI.getDefaultWorkspace()
      setWorkspaceId(workspace.id)
    } catch (error) {
      console.error('Failed to load workspace:', error)
    }
  }

  const loadLogs = async () => {
    try {
      setLoading(true)
      const params = {
        ...filters,
      }
      // Don't filter by workspace_id by default - show all user logs
      // Only filter by workspace if user explicitly wants to
      // if (workspaceId) params.workspaceId = workspaceId
      if (!params.startDate) delete params.startDate
      if (!params.endDate) delete params.endDate
      if (!params.actionType) delete params.actionType
      if (!params.resourceType) delete params.resourceType
      const response = await activityLogsAPI.getLogs(params)
      console.log('Activity logs response:', response)
      setLogs(Array.isArray(response) ? response : [])
    } catch (error) {
      console.error('Failed to load activity logs:', error)
      setLogs([])
    } finally {
      setLoading(false)
    }
  }

  const loadStats = async () => {
    if (!workspaceId) return // Stats require workspace
    try {
      const response = await activityLogsAPI.getStats(workspaceId, 30)
      setStats(response)
    } catch (error) {
      console.error('Failed to load stats:', error)
    }
  }

  const formatDate = (dateString) => {
    if (!dateString) return ''
    return new Date(dateString).toLocaleString()
  }

  const getActionIcon = (actionType) => {
    const icons = {
      file_upload: '📤',
      file_delete: '🗑️',
      extraction_start: '⚙️',
      extraction_retry: '🔄',
      payee_correct: '✏️',
      transaction_sync: '💾',
      login: '🔐',
      logout: '🚪',
      export_data: '📥',
    }
    return icons[actionType] || '📝'
  }

  const formatDetails = (details, actionType) => {
    if (!details || Object.keys(details).length === 0) return null

    const formatted = []

    switch (actionType) {
      case 'login':
        if (details.email) {
          formatted.push(
            <div key="email" className="flex items-center gap-2">
              <span className="text-gray-500">Email:</span>
              <strong className="text-gray-900">{details.email}</strong>
            </div>
          )
        }
        break

      case 'file_upload':
        const fileItems = []
        if (details.filename) {
          fileItems.push(
            <div key="filename" className="flex items-center gap-2">
              <span className="text-gray-500">File:</span>
              <strong className="text-gray-900">{details.filename}</strong>
            </div>
          )
        }
        if (details.file_type) {
          fileItems.push(
            <div key="type" className="flex items-center gap-2">
              <span className="text-gray-500">Type:</span>
              <strong className="text-gray-900">{details.file_type.toUpperCase()}</strong>
            </div>
          )
        }
        if (details.file_size) {
          const sizeMB = (details.file_size / (1024 * 1024)).toFixed(2)
          fileItems.push(
            <div key="size" className="flex items-center gap-2">
              <span className="text-gray-500">Size:</span>
              <strong className="text-gray-900">{sizeMB} MB</strong>
            </div>
          )
        }
        formatted.push(...fileItems)
        break

      case 'file_delete':
        if (details.filename) {
          formatted.push(
            <div key="filename" className="flex items-center gap-2">
              <span className="text-gray-500">Deleted:</span>
              <strong className="text-gray-900">{details.filename}</strong>
            </div>
          )
        }
        break

      case 'extraction_start':
      case 'extraction_retry':
        if (details.filename) {
          formatted.push(
            <div key="filename" className="flex items-center gap-2">
              <span className="text-gray-500">Processing:</span>
              <strong className="text-gray-900">{details.filename}</strong>
            </div>
          )
        }
        break

      case 'payee_correct':
        if (details.original_payee && details.corrected_payee) {
          formatted.push(
            <div key="payee" className="space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="text-gray-500">From:</span>
                <strong className="text-red-600">{details.original_payee}</strong>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-gray-500">To:</span>
                <strong className="text-green-600">{details.corrected_payee}</strong>
              </div>
              {details.similarity_score && (
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-gray-500">Similarity:</span>
                  <span className="text-gray-600">{details.similarity_score}%</span>
                </div>
              )}
            </div>
          )
        }
        break

      case 'transaction_sync':
        if (details.approved_count !== undefined) {
          formatted.push(
            <div key="count" className="flex items-center gap-2">
              <span className="text-gray-500">Approved:</span>
              <strong className="text-gray-900">{details.approved_count} transaction(s)</strong>
            </div>
          )
        }
        break

      case 'export_data':
        const exportItems = []
        if (details.export_type) {
          exportItems.push(
            <div key="type" className="flex items-center gap-2">
              <span className="text-gray-500">Format:</span>
              <strong className="text-gray-900">{details.export_type.toUpperCase()}</strong>
            </div>
          )
        }
        if (details.transaction_count) {
          exportItems.push(
            <div key="count" className="flex items-center gap-2">
              <span className="text-gray-500">Transactions:</span>
              <strong className="text-gray-900">{details.transaction_count}</strong>
            </div>
          )
        }
        formatted.push(...exportItems)
        break

      default:
        // For unknown action types, show key-value pairs in a readable format
        Object.entries(details).forEach(([key, value]) => {
          const displayKey = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
          if (typeof value === 'object' && value !== null) {
            formatted.push(
              <div key={key} className="text-xs">
                {displayKey}: <strong>{JSON.stringify(value)}</strong>
              </div>
            )
          } else {
            formatted.push(
              <span key={key}>
                {displayKey}: <strong>{String(value)}</strong>
              </span>
            )
          }
        })
    }

    if (formatted.length === 0) return null

    return (
      <div className="mt-2 space-y-1.5">
        {formatted}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Activity Logs</h1>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className="flex items-center gap-2 px-3 py-2 text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg"
        >
          <FaFilter />
          Filters
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Card className="p-4">
            <div className="flex items-center">
              <FaChartBar className="text-2xl text-blue-600 mr-3" />
              <div>
                <p className="text-sm font-medium text-gray-500">Total Activities</p>
                <p className="text-2xl font-bold text-gray-900">{stats.total_activities || 0}</p>
                <p className="text-xs text-gray-500">Last {stats.period_days} days</p>
              </div>
            </div>
          </Card>
          <Card className="p-4">
            <div>
              <p className="text-sm font-medium text-gray-500 mb-2">Top Actions</p>
              {Object.entries(stats.action_counts || {}).slice(0, 3).map(([action, count]) => (
                <div key={action} className="flex justify-between text-sm">
                  <span className="text-gray-600">{action.replace('_', ' ')}</span>
                  <span className="font-semibold">{count}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* Filters */}
      {showFilters && (
        <Card>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Action Type</label>
              <select
                value={filters.actionType}
                onChange={(e) => setFilters({ ...filters, actionType: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              >
                <option value="">All Actions</option>
                <option value="file_upload">File Upload</option>
                <option value="file_delete">File Delete</option>
                <option value="extraction_start">Extraction Start</option>
                <option value="extraction_retry">Extraction Retry</option>
                <option value="payee_correct">Payee Correct</option>
                <option value="transaction_sync">Transaction Sync</option>
                <option value="login">Login</option>
                <option value="logout">Logout</option>
                <option value="export_data">Export Data</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Resource Type</label>
              <input
                type="text"
                value={filters.resourceType}
                onChange={(e) => setFilters({ ...filters, resourceType: e.target.value })}
                placeholder="file, transaction, etc."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Start Date</label>
              <input
                type="date"
                value={filters.startDate}
                onChange={(e) => setFilters({ ...filters, startDate: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">End Date</label>
              <input
                type="date"
                value={filters.endDate}
                onChange={(e) => setFilters({ ...filters, endDate: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              />
            </div>
          </div>
        </Card>
      )}

      {/* Logs List */}
      <Card>
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : logs.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <p>No activity logs found</p>
          </div>
        ) : (
          <div className="space-y-2">
            {logs.map((log) => (
              <div
                key={log.id}
                className="p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-3 flex-1">
                    <span className="text-2xl">{getActionIcon(log.action_type)}</span>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-gray-900">
                          {log.action_type.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                        </span>
                        {log.resource_type && (
                          <span className="text-sm text-gray-500">
                            ({log.resource_type} #{log.resource_id})
                          </span>
                        )}
                      </div>
                      {formatDetails(log.details, log.action_type)}
                      <div className="mt-1 text-xs text-gray-500">
                        {formatDate(log.created_at)}
                        {log.ip_address && ` • IP: ${log.ip_address}`}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}

export default ActivityLogs
