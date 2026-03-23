import { useState, useEffect } from 'react'
import { ocrLogsAPI } from '../utils/api'
import Card from '../components/Card'
import Button from '../components/Button'
import { FaDownload, FaRedo, FaFilter } from 'react-icons/fa'

const OCRLogs = () => {
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [lines, setLines] = useState(500)
  const [level, setLevel] = useState('')
  const [fileId, setFileId] = useState('')
  const [logInfo, setLogInfo] = useState(null)
  const [autoRefresh, setAutoRefresh] = useState(false)

  useEffect(() => {
    loadLogInfo()
    loadLogs()
  }, [])

  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(() => {
        loadLogs()
      }, 5000) // Refresh every 5 seconds
      return () => clearInterval(interval)
    }
  }, [autoRefresh, lines, level, fileId])

  const loadLogInfo = async () => {
    try {
      const info = await ocrLogsAPI.getLogInfo()
      setLogInfo(info)
    } catch (err) {
      console.error('Failed to load log info:', err)
    }
  }

  const loadLogs = async () => {
    try {
      setLoading(true)
      setError('')
      const response = await ocrLogsAPI.getOCRLogs(
        lines,
        level || null,
        fileId ? parseInt(fileId) : null
      )
      console.log('OCR logs response:', response)
      setLogs(response.logs || [])
    } catch (err) {
      console.error('Failed to load OCR logs:', err)
      setError(err.message || 'Failed to load OCR logs')
      setLogs([])
    } finally {
      setLoading(false)
    }
  }

  const getLevelColor = (level) => {
    if (!level) return 'text-gray-600'
    const levelUpper = level.toUpperCase()
    if (levelUpper === 'ERROR') return 'text-red-600'
    if (levelUpper === 'WARNING') return 'text-yellow-600'
    if (levelUpper === 'INFO') return 'text-blue-600'
    if (levelUpper === 'DEBUG') return 'text-gray-500'
    return 'text-gray-600'
  }

  const downloadLogs = () => {
    const logText = logs.map(log => log.raw).join('\n')
    const blob = new Blob([logText], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `ocr-logs-${new Date().toISOString().split('T')[0]}.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">OCR Logs</h1>
        <div className="flex items-center gap-2">
          <Button
            onClick={loadLogs}
            variant="secondary"
            disabled={loading}
            className="flex items-center gap-2"
          >
            <FaRedo className={loading ? 'animate-spin' : ''} />
            Refresh
          </Button>
          <Button
            onClick={downloadLogs}
            variant="secondary"
            disabled={logs.length === 0}
            className="flex items-center gap-2"
          >
            <FaDownload />
            Download
          </Button>
        </div>
      </div>

      {logInfo && (
        <Card>
          <div className="text-sm text-gray-600">
            <p><strong>Log File:</strong> {logInfo.log_file_path}</p>
            <p><strong>Exists:</strong> {logInfo.ocr_log_exists ? 'Yes' : 'No'}</p>
          </div>
        </Card>
      )}

      {/* Filters */}
      <Card>
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <FaFilter />
            <h2 className="text-lg font-semibold text-gray-900">Filters</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Lines
              </label>
              <input
                type="number"
                value={lines}
                onChange={(e) => setLines(parseInt(e.target.value) || 500)}
                min="1"
                max="5000"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Level
              </label>
              <select
                value={level}
                onChange={(e) => setLevel(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              >
                <option value="">All Levels</option>
                <option value="INFO">INFO</option>
                <option value="ERROR">ERROR</option>
                <option value="WARNING">WARNING</option>
                <option value="DEBUG">DEBUG</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                File ID
              </label>
              <input
                type="number"
                value={fileId}
                onChange={(e) => setFileId(e.target.value)}
                placeholder="Filter by file ID"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              />
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                  className="h-4 w-4 text-blue-600"
                />
                <span className="text-sm text-gray-700">Auto-refresh</span>
              </label>
            </div>
          </div>
        </div>
      </Card>

      {/* Logs Display */}
      <Card>
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : logs.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <p>No logs found</p>
            {logInfo && !logInfo.ocr_log_exists && (
              <p className="text-sm mt-2">OCR log file does not exist yet. Logs will appear here once OCR operations start.</p>
            )}
            {logInfo && logInfo.ocr_log_exists && (
              <p className="text-sm mt-2">OCR log file exists but is empty. Logs will appear here once OCR operations start.</p>
            )}
          </div>
        ) : (
          <div className="space-y-2">
            <div className="text-sm text-gray-600 mb-4">
              Showing {logs.length} log entries
            </div>
            <div className="bg-gray-900 text-gray-100 p-4 rounded-lg font-mono text-xs overflow-x-auto max-h-[600px] overflow-y-auto">
              {logs.map((log, index) => (
                <div key={index} className="mb-1">
                  {log.level && (
                    <span className={getLevelColor(log.level)}>
                      [{log.level}]
                    </span>
                  )}
                  {log.timestamp && (
                    <span className="text-gray-400 ml-2">{log.timestamp}</span>
                  )}
                  <span className="ml-2">{log.message}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}

export default OCRLogs
