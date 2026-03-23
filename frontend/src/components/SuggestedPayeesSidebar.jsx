import { useState, useEffect } from 'react'
import { payeesAPI, workspacesAPI } from '../utils/api'
import { FaTimes, FaUser } from 'react-icons/fa'

const SuggestedPayeesSidebar = ({ isOpen, onClose, onSelectPayee, currentPayeeName = '' }) => {
  const [workspaceId, setWorkspaceId] = useState(null)
  const [suggestedPayees, setSuggestedPayees] = useState([])
  const [recentPayees, setRecentPayees] = useState([])
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('suggested') // 'suggested' or 'recent'

  useEffect(() => {
    if (isOpen && workspaceId) {
      loadPayees()
    }
  }, [isOpen, workspaceId])

  useEffect(() => {
    loadWorkspace()
  }, [])

  const loadWorkspace = async () => {
    try {
      const workspace = await workspacesAPI.getDefaultWorkspace()
      setWorkspaceId(workspace.id)
    } catch (error) {
      console.error('Failed to load workspace:', error)
    }
  }

  const loadPayees = async () => {
    if (!workspaceId) return
    
    try {
      setLoading(true)
      const [suggestions, recent] = await Promise.all([
        payeesAPI.getSuggestions(workspaceId, 10),
        payeesAPI.getRecent(workspaceId, 10)
      ])
      setSuggestedPayees(suggestions || [])
      setRecentPayees(recent || [])
    } catch (error) {
      console.error('Failed to load payees:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSelectPayee = (payee) => {
    if (onSelectPayee) {
      onSelectPayee(payee)
    }
    onClose()
  }

  if (!isOpen) return null

  const displayPayees = activeTab === 'suggested' ? suggestedPayees : recentPayees

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 bg-black bg-opacity-50 z-40"
        onClick={onClose}
      />
      
      {/* Sidebar */}
      <div className="fixed right-0 top-0 h-full w-80 bg-white shadow-xl z-50 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Suggested Payees</h2>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 transition-colors"
            title="Close"
          >
            <FaTimes />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200">
          <button
            onClick={() => setActiveTab('suggested')}
            className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
              activeTab === 'suggested'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            Suggested ({suggestedPayees.length})
          </button>
          <button
            onClick={() => setActiveTab('recent')}
            className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
              activeTab === 'recent'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            Recent ({recentPayees.length})
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            </div>
          ) : displayPayees.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <FaUser className="mx-auto text-4xl text-gray-300 mb-2" />
              <p>No {activeTab === 'suggested' ? 'suggested' : 'recent'} payees</p>
            </div>
          ) : (
            <div className="space-y-2">
              {displayPayees.map((payee) => {
                const isCurrent = currentPayeeName && 
                  payee.display_name.toLowerCase() === currentPayeeName.toLowerCase()
                
                return (
                  <button
                    key={payee.id}
                    onClick={() => handleSelectPayee(payee)}
                    className={`w-full text-left p-3 rounded-lg border transition-colors ${
                      isCurrent
                        ? 'bg-blue-50 border-blue-300'
                        : 'bg-gray-50 border-gray-200 hover:bg-gray-100 hover:border-gray-300'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className={`text-sm font-medium truncate ${
                          isCurrent ? 'text-blue-900' : 'text-gray-900'
                        }`}>
                          {payee.display_name}
                        </p>
                        {payee.usage_count > 0 && (
                          <p className="text-xs text-gray-500 mt-1">
                            Used {payee.usage_count} {payee.usage_count === 1 ? 'time' : 'times'}
                          </p>
                        )}
                        {payee.vendor_id && (
                          <p className="text-xs text-blue-600 mt-1">Has vendor</p>
                        )}
                        {payee.category_id && (
                          <p className="text-xs text-green-600 mt-1">Has category</p>
                        )}
                      </div>
                      {isCurrent && (
                        <span className="ml-2 text-xs text-blue-600 font-medium">Current</span>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </>
  )
}

export default SuggestedPayeesSidebar

