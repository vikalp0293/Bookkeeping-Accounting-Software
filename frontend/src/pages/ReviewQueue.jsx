import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { reviewQueueAPI, workspacesAPI } from '../utils/api'
import Card from '../components/Card'
import Button from '../components/Button'
import { FaEye, FaCheck, FaTimes, FaFlag } from 'react-icons/fa'

const ReviewQueue = () => {
  const navigate = useNavigate()
  const [workspaceId, setWorkspaceId] = useState(null)
  const [items, setItems] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('pending')
  const [priorityFilter, setPriorityFilter] = useState('')

  useEffect(() => {
    loadWorkspace()
  }, [])

  useEffect(() => {
    if (workspaceId) {
      loadQueue()
      loadStats()
    }
  }, [workspaceId, statusFilter, priorityFilter])

  const loadWorkspace = async () => {
    try {
      const workspace = await workspacesAPI.getDefaultWorkspace()
      setWorkspaceId(workspace.id)
    } catch (error) {
      console.error('Failed to load workspace:', error)
    }
  }

  const loadQueue = async () => {
    if (!workspaceId) {
      console.log('⚠️ Cannot load queue: workspaceId is not set')
      return
    }
    try {
      setLoading(true)
      console.log('📋 Loading review queue with:', { workspaceId, statusFilter, priorityFilter })
      const queueItems = await reviewQueueAPI.getQueue(
        workspaceId,
        statusFilter,
        priorityFilter || null
      )
      console.log('✅ Review queue loaded:', queueItems)
      setItems(queueItems || [])
    } catch (error) {
      console.error('❌ Failed to load review queue:', error)
      setItems([])
    } finally {
      setLoading(false)
    }
  }

  const loadStats = async () => {
    try {
      const statistics = await reviewQueueAPI.getStats(workspaceId)
      setStats(statistics)
    } catch (error) {
      console.error('Failed to load stats:', error)
    }
  }

  const handleAssign = async (reviewId) => {
    try {
      await reviewQueueAPI.assignReview(reviewId)
      loadQueue()
      loadStats()
    } catch (error) {
      alert(`Failed to assign review: ${error.message}`)
    }
  }

  const handleUpdateStatus = async (reviewId, status) => {
    try {
      await reviewQueueAPI.updateReview(reviewId, status)
      loadQueue()
      loadStats()
    } catch (error) {
      alert(`Failed to update status: ${error.message}`)
    }
  }

  const getPriorityColor = (priority) => {
    switch (priority) {
      case 'high':
        return 'bg-red-100 text-red-800'
      case 'medium':
        return 'bg-yellow-100 text-yellow-800'
      case 'low':
        return 'bg-blue-100 text-blue-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'pending':
        return 'bg-gray-100 text-gray-800'
      case 'in_review':
        return 'bg-blue-100 text-blue-800'
      case 'approved':
        return 'bg-green-100 text-green-800'
      case 'completed':
        return 'bg-green-100 text-green-800'
      case 'rejected':
        return 'bg-red-100 text-red-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  const getReasonLabel = (reason) => {
    const labels = {
      low_confidence: 'Low Confidence',
      missing_fields: 'Missing Fields',
      non_english: 'Non-English',
      no_payee_match: 'No Payee Match',
      user_flagged: 'User Flagged',
      payee_correction: 'Payee Correction',
      other: 'Other',
    }
    return labels[reason] || reason
  }

  if (loading && !items.length) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Review Queue</h1>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          <Card className="p-4">
            <div className="text-sm font-medium text-gray-500">Total</div>
            <div className="text-2xl font-bold text-gray-900">{stats.total}</div>
          </Card>
          <Card className="p-4">
            <div className="text-sm font-medium text-gray-500">Pending</div>
            <div className="text-2xl font-bold text-yellow-600">{stats.pending}</div>
          </Card>
          <Card className="p-4">
            <div className="text-sm font-medium text-gray-500">In Review</div>
            <div className="text-2xl font-bold text-blue-600">{stats.in_review}</div>
          </Card>
          <Card className="p-4">
            <div className="text-sm font-medium text-gray-500">Completed</div>
            <div className="text-2xl font-bold text-green-600">{stats.completed}</div>
          </Card>
        </div>
      )}

      {/* Filters */}
      <Card>
        <div className="flex flex-wrap gap-4 items-center">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Status
            </label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              <option value="pending">Pending</option>
              <option value="in_review">In Review</option>
              <option value="approved">Approved</option>
              <option value="completed">Completed</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Priority
            </label>
            <select
              value={priorityFilter}
              onChange={(e) => setPriorityFilter(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              <option value="">All</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
        </div>
      </Card>

      {/* Review Items */}
      <Card title="Review Items">
        {loading ? (
          <div className="text-center py-8 text-gray-500">
            Loading...
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            No items in review queue
          </div>
        ) : (
          <div className="space-y-4">
            {items.map((item) => (
              <div
                key={item.id}
                className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <span
                        className={`px-2 py-1 text-xs font-semibold rounded-full ${getPriorityColor(
                          item.priority
                        )}`}
                      >
                        {item.priority}
                      </span>
                      <span
                        className={`px-2 py-1 text-xs font-semibold rounded-full ${getStatusColor(
                          item.status
                        )}`}
                      >
                        {item.status}
                      </span>
                      <span className="px-2 py-1 text-xs font-medium text-gray-600 bg-gray-100 rounded-full">
                        {getReasonLabel(item.review_reason)}
                      </span>
                    </div>
                    <div className="text-sm text-gray-600">
                      File ID: {item.file_id}
                      {item.transaction_id && ` • Transaction: ${item.transaction_id}`}
                    </div>
                    {item.notes && (
                      <div className="mt-2 text-sm text-gray-500 italic">
                        {item.notes}
                      </div>
                    )}
                    <div className="mt-2 text-xs text-gray-400">
                      Created: {new Date(item.created_at).toLocaleString()}
                    </div>
                  </div>
                  <div className="flex gap-2 ml-4">
                    <Link
                      to={`/extracted/${item.file_id}`}
                      className="p-2 text-blue-600 hover:text-blue-900"
                      title="View file"
                    >
                      <FaEye />
                    </Link>
                    {item.status === 'pending' && (
                      <button
                        onClick={() => handleAssign(item.id)}
                        className="p-2 text-green-600 hover:text-green-900"
                        title="Assign to me"
                      >
                        <FaFlag />
                      </button>
                    )}
                    {item.status === 'in_review' && (
                      <>
                        <button
                          onClick={() => handleUpdateStatus(item.id, 'approved')}
                          className="p-2 text-green-600 hover:text-green-900"
                          title="Approve"
                        >
                          <FaCheck />
                        </button>
                        <button
                          onClick={() => handleUpdateStatus(item.id, 'rejected')}
                          className="p-2 text-red-600 hover:text-red-900"
                          title="Reject"
                        >
                          <FaTimes />
                        </button>
                      </>
                    )}
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

export default ReviewQueue

