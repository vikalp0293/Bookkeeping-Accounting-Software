import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { dashboardAPI, filesAPI, extractionAPI } from '../utils/api'
import Card from '../components/Card'
import Button from '../components/Button'
import { FaEye, FaTrash, FaTimes, FaRedo } from 'react-icons/fa'

const Dashboard = () => {
  const navigate = useNavigate()
  const [stats, setStats] = useState(null)
  const [files, setFiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [deletingId, setDeletingId] = useState(null)
  const [retryingId, setRetryingId] = useState(null)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      setLoading(true)
      const [statsData, filesData] = await Promise.all([
        dashboardAPI.getStats(),
        filesAPI.listFiles(),
      ])
      setStats(statsData)
      setFiles(filesData.slice(0, 5)) // Show latest 5 files
    } catch (err) {
      setError(err.message || 'Failed to load dashboard data')
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (fileId, filename) => {
    if (!window.confirm(`Are you sure you want to delete "${filename}"? This action cannot be undone.`)) {
      return
    }

    try {
      setDeletingId(fileId)
      await filesAPI.deleteFile(fileId)
      // Reload data after deletion
      await loadData()
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
      // Reload data to show updated status
      await loadData()
    } catch (err) {
      alert(`Failed to retry extraction: ${err.message}`)
    } finally {
      setRetryingId(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
        {error}
      </div>
    )
  }

  const statCards = [
    {
      title: 'Total Files',
      value: stats?.total_files || 0,
      icon: '📄',
      color: 'bg-blue-500',
    },
    {
      title: 'Successful',
      value: stats?.successful_extractions || 0,
      icon: '✅',
      color: 'bg-green-500',
    },
    {
      title: 'Pending',
      value: stats?.pending_extractions || 0,
      icon: '⏳',
      color: 'bg-yellow-500',
    },
    {
      title: 'Failed',
      value: stats?.failed_extractions || 0,
      icon: '❌',
      color: 'bg-red-500',
    },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <Link
          to="/upload"
          className="mt-4 sm:mt-0 btn-primary inline-block text-center"
        >
          Upload File
        </Link>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((stat, index) => (
          <Card key={index} className="p-6">
            <div className="flex items-center">
              <div className={`${stat.color} p-3 rounded-lg text-white text-2xl`}>
                {stat.icon}
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500">{stat.title}</p>
                <p className="text-2xl font-bold text-gray-900">{stat.value}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Recent Files */}
      <Card title="Recent Files" subtitle="Latest uploaded files">
        {files.length === 0 ? (
          <p className="text-gray-500 text-center py-8">No files uploaded yet</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    File Name
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Type
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Date
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {files.map((file) => (
                  <tr key={file.id} className="hover:bg-gray-50">
                    <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-900">
                      {file.original_filename}
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-500">
                      {file.file_type.toUpperCase()}
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <span
                        className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${
                          file.status === 'completed'
                            ? 'bg-green-100 text-green-800'
                            : file.status === 'processing'
                            ? 'bg-yellow-100 text-yellow-800'
                            : file.status === 'failed'
                            ? 'bg-red-100 text-red-800'
                            : 'bg-gray-100 text-gray-800'
                        }`}
                      >
                        {file.status}
                      </span>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(file.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap text-sm">
                      <div className="flex items-center gap-3">
                        {file.status === 'completed' && (
                          <Link
                            to={`/extracted/${file.id}`}
                            className="text-blue-600 hover:text-blue-900 flex items-center"
                            title="View extraction results"
                          >
                            <FaEye className="text-base" />
                          </Link>
                        )}
                        {file.status === 'failed' && (
                          <button
                            onClick={() => handleRetry(file.id, file.original_filename)}
                            disabled={retryingId === file.id}
                            className="text-green-600 hover:text-green-900 disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
                            title={retryingId === file.id ? 'Retrying...' : 'Retry extraction'}
                          >
                            <FaRedo className={`text-base ${retryingId === file.id ? 'animate-spin' : ''}`} />
                          </button>
                        )}
                        <button
                          onClick={() => handleDelete(file.id, file.original_filename)}
                          disabled={deletingId === file.id}
                          className="text-red-600 hover:text-red-900 disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
                          title={deletingId === file.id ? 'Deleting...' : 'Delete file'}
                        >
                          <FaTrash className="text-base" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}

export default Dashboard

