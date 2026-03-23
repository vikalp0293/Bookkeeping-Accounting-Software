import { useState, useEffect } from 'react'
import { payeeManagementAPI, workspacesAPI } from '../utils/api'
import Card from '../components/Card'
import Button from '../components/Button'
import Input from '../components/Input'
import { FaSearch, FaEdit, FaTrash, FaPlus, FaHistory } from 'react-icons/fa'

const PayeeManagement = () => {
  const [payees, setPayees] = useState([])
  const [loading, setLoading] = useState(true)
  const [workspaceId, setWorkspaceId] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedPayee, setSelectedPayee] = useState(null)
  const [showEditModal, setShowEditModal] = useState(false)
  const [showCorrections, setShowCorrections] = useState(false)
  const [corrections, setCorrections] = useState([])
  const [editPayeeName, setEditPayeeName] = useState('')
  const [editAliases, setEditAliases] = useState('')
  const [editQbExpenseAccount, setEditQbExpenseAccount] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    loadWorkspace()
  }, [])

  useEffect(() => {
    if (workspaceId) {
      loadPayees()
    }
  }, [workspaceId])

  const loadWorkspace = async () => {
    try {
      const workspace = await workspacesAPI.getDefaultWorkspace()
      setWorkspaceId(workspace.id)
    } catch (error) {
      console.error('Failed to load workspace:', error)
    }
  }

  const loadPayees = async () => {
    try {
      setLoading(true)
      const response = await payeeManagementAPI.getPayees(workspaceId, 100)
      setPayees(response || [])
    } catch (error) {
      console.error('Failed to load payees:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadCorrections = async (payeeId) => {
    try {
      const response = await payeeManagementAPI.getPayeeCorrections(workspaceId, payeeId)
      console.log('Corrections response:', response)
      setCorrections(Array.isArray(response) ? response : [])
      setShowCorrections(true)
    } catch (error) {
      console.error('Failed to load corrections:', error)
      setCorrections([])
      setShowCorrections(true) // Still show modal even if empty/error
    }
  }

  const handleEditClick = (payee) => {
    setSelectedPayee(payee)
    setEditPayeeName(payee.display_name)
    setEditAliases(payee.aliases ? payee.aliases.join(', ') : '')
    setEditQbExpenseAccount(payee.qb_expense_account_name || '')
    setShowEditModal(true)
  }

  const handleSaveEdit = async () => {
    if (!selectedPayee || !editPayeeName.trim()) {
      alert('Payee name cannot be empty')
      return
    }

    try {
      setSaving(true)
      const aliasesArray = editAliases
        .split(',')
        .map(a => a.trim())
        .filter(a => a.length > 0)

      const updatedPayee = await payeeManagementAPI.updatePayee(workspaceId, selectedPayee.id, {
        display_name: editPayeeName.trim(),
        aliases: aliasesArray.length > 0 ? aliasesArray : null,
        qb_expense_account_name: editQbExpenseAccount.trim() || null
      })

      // Reload payees to show updated data
      await loadPayees()
      setShowEditModal(false)
      setSelectedPayee(null)
      setEditPayeeName('')
      setEditAliases('')
      setEditQbExpenseAccount('')

      // Show success message
      alert(`Payee "${updatedPayee.display_name}" has been updated successfully!`)
    } catch (error) {
      console.error('Failed to update payee:', error)
      const errorMessage = error.response?.data?.detail || error.message || 'Failed to update payee'
      alert(errorMessage)
    } finally {
      setSaving(false)
    }
  }

  const handleDeletePayee = async (payee) => {
    if (!window.confirm(`Delete payee "${payee.display_name}"? This action cannot be undone.`)) {
      return
    }

    try {
      await payeeManagementAPI.deletePayee(workspaceId, payee.id)
      // Reload payees to show updated list
      await loadPayees()
    } catch (error) {
      console.error('Failed to delete payee:', error)
      alert(error.message || 'Failed to delete payee')
    }
  }

  const filteredPayees = payees.filter(payee =>
    payee.display_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    payee.normalized_name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Payee Management</h1>
        <Button variant="primary" className="flex items-center gap-2">
          <FaPlus />
          Add Payee
        </Button>
      </div>

      {/* Search */}
      <Card>
        <div className="relative">
          <FaSearch className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search payees..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </Card>

      {/* Payees List */}
      <Card>
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : filteredPayees.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <p>No payees found</p>
          </div>
        ) : (
          <div className="space-y-2">
            {filteredPayees.map((payee) => (
              <div
                key={payee.id}
                className="p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <h3 className="font-semibold text-gray-900">{payee.display_name}</h3>
                      <span className="text-sm text-gray-500">
                        Used {payee.usage_count} time{payee.usage_count !== 1 ? 's' : ''}
                      </span>
                    </div>
                    {payee.aliases && payee.aliases.length > 0 && (
                      <div className="mt-1 text-sm text-gray-600">
                        <strong>Aliases:</strong> {payee.aliases.join(', ')}
                      </div>
                    )}
                    {payee.qb_expense_account_name ? (
                      <div className="mt-1 text-sm text-green-700">
                        <strong>QB Expense Account:</strong> {payee.qb_expense_account_name}
                      </div>
                    ) : (
                      <div className="mt-1 text-sm text-amber-600">
                        <strong>QB Expense Account:</strong> Not set (required for Sync to QuickBooks)
                      </div>
                    )}
                    {payee.normalized_name !== payee.display_name.toLowerCase() && (
                      <div className="mt-1 text-xs text-gray-500">
                        Normalized: {payee.normalized_name}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => {
                        setSelectedPayee(payee)
                        loadCorrections(payee.id)
                      }}
                      className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg"
                      title="View correction history"
                    >
                      <FaHistory />
                    </button>
                    <button
                      onClick={() => handleEditClick(payee)}
                      className="p-2 text-gray-600 hover:bg-gray-100 rounded-lg"
                      title="Edit payee"
                    >
                      <FaEdit />
                    </button>
                    <button
                      onClick={() => handleDeletePayee(payee)}
                      className="p-2 text-red-600 hover:bg-red-50 rounded-lg"
                      title="Delete payee"
                    >
                      <FaTrash />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Edit Modal */}
      {showEditModal && selectedPayee && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <Card className="max-w-lg w-full mx-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold">Edit Payee</h2>
              <button
                onClick={() => {
                  setShowEditModal(false)
                  setSelectedPayee(null)
                  setEditPayeeName('')
                  setEditAliases('')
                  setEditQbExpenseAccount('')
                }}
                className="text-gray-500 hover:text-gray-700"
              >
                ✕
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Payee Name *
                </label>
                <Input
                  type="text"
                  value={editPayeeName}
                  onChange={(e) => setEditPayeeName(e.target.value)}
                  placeholder="Enter payee name"
                  className="w-full"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Aliases (comma-separated)
                </label>
                <Input
                  type="text"
                  value={editAliases}
                  onChange={(e) => setEditAliases(e.target.value)}
                  placeholder="e.g., Alias1, Alias2, Alias3"
                  className="w-full"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Separate multiple aliases with commas
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  QuickBooks Expense Account
                </label>
                <Input
                  type="text"
                  value={editQbExpenseAccount}
                  onChange={(e) => setEditQbExpenseAccount(e.target.value)}
                  placeholder="e.g., Rent Expense, Utilities, Bank Service Charges"
                  className="w-full"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Must match an expense account name in your QuickBooks Chart of Accounts. Required for withdrawal/check sync.
                </p>
              </div>
              <div className="flex items-center gap-2 pt-2">
                <Button
                  variant="primary"
                  onClick={handleSaveEdit}
                  disabled={saving || !editPayeeName.trim()}
                  className="flex-1"
                >
                  {saving ? 'Saving...' : 'Save Changes'}
                </Button>
                <Button
                  variant="secondary"
                onClick={() => {
                  setShowEditModal(false)
                  setSelectedPayee(null)
                  setEditPayeeName('')
                  setEditAliases('')
                  setEditQbExpenseAccount('')
                }}
                  disabled={saving}
                >
                  Cancel
                </Button>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* Corrections Modal */}
      {showCorrections && selectedPayee && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <Card className="max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold">Correction History: {selectedPayee.display_name}</h2>
              <button
                onClick={() => {
                  setShowCorrections(false)
                  setSelectedPayee(null)
                }}
                className="text-gray-500 hover:text-gray-700"
              >
                ✕
              </button>
            </div>
            {corrections.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-gray-500 mb-2">No corrections found for this payee</p>
                <p className="text-xs text-gray-400">
                  Corrections are created when you correct a payee name during extraction or review.
                  <br />
                  Editing a payee name here does not create a correction record.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {corrections.map((correction) => (
                  <div key={correction.id} className="p-3 bg-gray-50 rounded-lg">
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-gray-600 font-medium">{correction.original_payee}</span>
                          <span className="text-gray-400">→</span>
                          <span className="font-semibold text-green-700">{correction.corrected_payee}</span>
                        </div>
                        {correction.file_id && (
                          <div className="text-xs text-gray-500 mt-1">
                            File ID: {correction.file_id}
                            {correction.transaction_id && ` • Transaction: ${correction.transaction_id}`}
                          </div>
                        )}
                        {correction.correction_reason && (
                          <div className="text-xs text-gray-500 mt-1">
                            Reason: {correction.correction_reason}
                          </div>
                        )}
                      </div>
                      <div className="text-right ml-4">
                        <div className="text-xs text-gray-500">
                          {new Date(correction.created_at).toLocaleDateString()}
                        </div>
                        {correction.similarity_score && (
                          <div className="text-xs text-gray-500 mt-1">
                            Similarity: {correction.similarity_score.toFixed(1)}%
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}

export default PayeeManagement
