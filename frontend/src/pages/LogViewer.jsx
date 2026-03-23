import { useState } from 'react'
import { Link } from 'react-router-dom'
import Card from '../components/Card'
import { FaFileAlt, FaUser, FaCog } from 'react-icons/fa'

const LogViewer = () => {
  const [activeTab, setActiveTab] = useState('overview')

  const logTypes = [
    { id: 'ocr', name: 'OCR Logs', icon: FaFileAlt, path: '/logs/ocr', description: 'View OCR processing logs' },
    { id: 'activity', name: 'Activity Logs', icon: FaUser, path: '/logs/activity', description: 'View user activity logs' },
    { id: 'qbwc', name: 'QB Web Connector', icon: FaCog, path: '/api/v1/qbwc/logs', description: 'View QuickBooks sync logs', external: true },
  ]

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Log Viewer</h1>
      
      <Card>
        <p className="text-gray-600 mb-6">
          View and manage different types of logs in the system. Select a log type to view detailed logs.
        </p>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {logTypes.map((logType) => {
            const Icon = logType.icon
            return (
              <Link
                key={logType.id}
                to={logType.path}
                target={logType.external ? '_blank' : undefined}
                className="p-6 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors border border-gray-200"
              >
                <div className="flex items-start gap-4">
                  <div className="p-3 bg-blue-100 rounded-lg">
                    <Icon className="text-blue-600 text-xl" />
                  </div>
                  <div className="flex-1">
                    <h3 className="font-semibold text-gray-900 mb-1">{logType.name}</h3>
                    <p className="text-sm text-gray-600">{logType.description}</p>
                  </div>
                </div>
              </Link>
            )
          })}
        </div>
      </Card>
    </div>
  )
}

export default LogViewer
