import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { filesAPI, extractionAPI, qbQueueAPI, workspacesAPI, payeeManagementAPI, API_BASE_URL } from '../utils/api'
import { isElectron, electronAPI } from '../utils/electron-api'
import Card from '../components/Card'
import Button from '../components/Button'
import Input from '../components/Input'
import SuggestedPayeesSidebar from '../components/SuggestedPayeesSidebar'
import { FaTrash, FaTimes, FaFilePdf, FaTimesCircle, FaUsers, FaSync, FaDownload, FaRedo } from 'react-icons/fa'

// Component to display check data
const CheckDisplay = ({ data }) => {
  const formatCurrency = (amount) => {
    if (amount === null || amount === undefined) return 'N/A'
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(amount)
  }

  const formatDate = (dateStr) => {
    if (dateStr == null || dateStr === '') return 'N/A'
    try {
      let date
      const isoMatch = String(dateStr).match(/^(\d{4})-(\d{2})-(\d{2})/)
      if (isoMatch) {
        date = new Date(parseInt(isoMatch[1], 10), parseInt(isoMatch[2], 10) - 1, parseInt(isoMatch[3], 10))
      } else {
        date = new Date(dateStr)
      }
      if (Number.isNaN(date.getTime())) return String(dateStr)
      return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
    } catch {
      return String(dateStr)
    }
  }

  const getConfidenceColor = (confidence) => {
    if (confidence >= 70) return 'text-green-600 bg-green-50'
    if (confidence >= 50) return 'text-yellow-600 bg-yellow-50'
    return 'text-red-600 bg-red-50'
  }

  return (
    <div className="space-y-6">
      {/* OCR Confidence */}
      {data.confidence !== undefined && (
        <div className={`inline-block px-3 py-1 rounded-full text-xs font-semibold ${getConfidenceColor(data.confidence)}`}>
          OCR Confidence: {data.confidence.toFixed(1)}%
        </div>
      )}

      {/* Check Information Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Check Number */}
        <div className="bg-blue-50 rounded-lg p-4">
          <p className="text-xs font-medium text-blue-700 mb-1">Check Number</p>
          <p className="text-lg font-semibold text-blue-900">{data.check_number || 'N/A'}</p>
        </div>

        {/* Date */}
        <div className="bg-blue-50 rounded-lg p-4">
          <p className="text-xs font-medium text-blue-700 mb-1">Date</p>
          <p className="text-lg font-semibold text-blue-900">{formatDate(data.date)}</p>
        </div>

        {/* Payee */}
        <div className="bg-green-50 rounded-lg p-4">
          <p className="text-xs font-medium text-green-700 mb-1">Pay to the Order of</p>
          <p className="text-lg font-semibold text-green-900">{data.payee || 'N/A'}</p>
        </div>

        {/* Amount */}
        <div className="bg-green-50 rounded-lg p-4">
          <p className="text-xs font-medium text-green-700 mb-1">Amount</p>
          <p className="text-2xl font-bold text-green-900">{formatCurrency(data.amount)}</p>
        </div>
      </div>

      {/* Memo */}
      {data.memo && (
        <div className="bg-gray-50 rounded-lg p-4">
          <p className="text-xs font-medium text-gray-700 mb-1">Memo / For</p>
          <p className="text-sm text-gray-900">{data.memo}</p>
        </div>
      )}

      {/* Bank & Account Information */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Bank Information */}
        <div className="bg-gray-50 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Bank Information</h3>
          <div className="space-y-2 text-sm">
            {data.bank_name && (
              <div>
                <p className="text-gray-600">Bank Name</p>
                <p className="font-medium text-gray-900">{data.bank_name}</p>
              </div>
            )}
            {data.routing_number && (
              <div>
                <p className="text-gray-600">Routing Number</p>
                <p className="font-medium text-gray-900">{data.routing_number}</p>
              </div>
            )}
            {data.account_number && (
              <div>
                <p className="text-gray-600">Account Number</p>
                <p className="font-medium text-gray-900">{data.account_number}</p>
              </div>
            )}
          </div>
        </div>

        {/* Company Information */}
        <div className="bg-gray-50 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Company Information</h3>
          <div className="space-y-2 text-sm">
            {data.company_name && (
              <div>
                <p className="text-gray-600">Company Name</p>
                <p className="font-medium text-gray-900">{data.company_name}</p>
              </div>
            )}
            {data.address && (
              <div>
                <p className="text-gray-600">Address</p>
                <p className="font-medium text-gray-900">{data.address}</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Raw OCR Text (Collapsible) */}
      {data.raw_text && (
        <details className="bg-gray-50 rounded-lg p-4">
          <summary className="text-sm font-semibold text-gray-900 cursor-pointer hover:text-gray-700">
            View Raw OCR Text
          </summary>
          <pre className="mt-3 text-xs text-gray-600 whitespace-pre-wrap max-h-96 overflow-y-auto">
            {data.raw_text}
          </pre>
        </details>
      )}
    </div>
  )
}

// Component to display bank statement data
const BankStatementDisplay = ({ data, onRetry, retrying }) => {
  const formatCurrency = (amount) => {
    if (amount === null || amount === undefined) return 'N/A'
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(amount)
  }

  const formatDate = (dateStr) => {
    if (dateStr == null || dateStr === '') return 'N/A'
    try {
      let date
      // Parse YYYY-MM-DD as local date to avoid timezone shifting
      const isoMatch = String(dateStr).match(/^(\d{4})-(\d{2})-(\d{2})/)
      if (isoMatch) {
        date = new Date(parseInt(isoMatch[1], 10), parseInt(isoMatch[2], 10) - 1, parseInt(isoMatch[3], 10))
      } else {
        date = new Date(dateStr)
      }
      if (Number.isNaN(date.getTime())) return String(dateStr)
      return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
    } catch {
      return String(dateStr)
    }
  }

  return (
    <div className="space-y-6">
      {/* Account Information */}
      {(data.bank_name || data.account_number || data.account_name) && (
        <div className="bg-blue-50 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-blue-900 mb-3">Account Information</h3>
          <div className="grid grid-cols-2 gap-3 text-sm">
            {data.bank_name && (
              <div>
                <p className="text-blue-700 font-medium">Bank</p>
                <p className="text-blue-900">{data.bank_name}</p>
              </div>
            )}
            {data.account_number && (
              <div>
                <p className="text-blue-700 font-medium">Account Number</p>
                <p className="text-blue-900">{data.account_number}</p>
              </div>
            )}
            {data.account_name && (
              <div>
                <p className="text-blue-700 font-medium">Account Name</p>
                <p className="text-blue-900">{data.account_name}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Statement Period */}
      {(data.statement_period_start || data.statement_period_end) && (
        <div>
          <h3 className="text-sm font-semibold text-gray-900 mb-2">Statement Period</h3>
          <p className="text-sm text-gray-600">
            {formatDate(data.statement_period_start)} - {formatDate(data.statement_period_end)}
          </p>
        </div>
      )}

      {/* Balances */}
      {(data.beginning_balance !== null || data.ending_balance !== null) && (
        <div className="grid grid-cols-2 gap-4">
          {data.beginning_balance !== null && (
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500">Beginning Balance</p>
              <p className="text-lg font-semibold text-gray-900">{formatCurrency(data.beginning_balance)}</p>
            </div>
          )}
          {data.ending_balance !== null && (
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500">Ending Balance</p>
              <p className="text-lg font-semibold text-gray-900">{formatCurrency(data.ending_balance)}</p>
            </div>
          )}
        </div>
      )}

      {/* Transactions */}
      {data.transactions && data.transactions.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-900 mb-3">
            Transactions ({data.transactions.length})
          </h3>
          <div className="overflow-x-auto overflow-y-auto max-h-[600px] border border-gray-200 rounded-lg">
            <table className="w-full divide-y divide-gray-200 table-fixed">
              <thead className="bg-gray-50 sticky top-0 z-10">
                <tr>
                  <th className="w-24 px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
                  <th className="w-20 px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Check #</th>
                  <th className="min-w-[140px] max-w-[220px] px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Payee/Depositor</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
                  <th className="w-28 px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                  <th className="w-24 px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">Amount</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {data.transactions.map((trans, index) => {
                  // Check #: prefer reference_number (API may use reference_number or referenceNumber)
                  const refNum = trans.reference_number ?? trans.referenceNumber ?? trans['reference_number']
                  const desc = trans.description ?? trans.memo ?? ''
                  const descStr = String(desc)
                  const checkMatch = descStr && descStr.match(/Check\s*#?\s*(\d{3,6})/i)
                  const leadingCheckMatch = descStr && descStr.match(/^\s*(\d{4,6})\*?\s+/)
                  const checkNum = refNum ?? (checkMatch ? checkMatch[1] : null) ?? (leadingCheckMatch ? leadingCheckMatch[1] : null)
                  const displayPayee = trans.payee || trans.depositor || (checkNum ? `Check #${checkNum}` : null) || 'N/A'
                  return (
                  <tr key={index} className="hover:bg-gray-50">
                    <td className="px-3 py-2 text-sm text-gray-900">
                      {formatDate(trans.date ?? trans.transaction_date) || 'N/A'}
                    </td>
                    <td className="px-3 py-2 text-sm text-gray-600">
                      {checkNum || '—'}
                    </td>
                    <td className="px-3 py-2 text-sm font-medium text-gray-900 break-words align-top" title={displayPayee}>
                      <span className="line-clamp-3" title={displayPayee}>{displayPayee}</span>
                    </td>
                    <td className="px-3 py-2 text-sm text-gray-900 truncate" title={trans.description}>
                      {trans.description || 'N/A'}
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={`px-2 py-1 text-xs font-semibold rounded-full ${
                          trans.transaction_type === 'DEPOSIT'
                            ? 'bg-green-100 text-green-800'
                            : trans.transaction_type === 'WITHDRAWAL' || trans.transaction_type === 'CHECK'
                            ? 'bg-red-100 text-red-800'
                            : 'bg-gray-100 text-gray-800'
                        }`}
                      >
                        {trans.transaction_type || 'N/A'}
                      </span>
                    </td>
                    <td className={`px-3 py-2 text-sm text-right font-medium ${
                      trans.amount >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {formatCurrency(Math.abs(trans.amount))}
                    </td>
                  </tr>
                )})}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Summary if no transactions but has totals */}
      {(!data.transactions || data.transactions.length === 0) && (
        <div className="text-center py-4 text-gray-500 text-sm">
          No transactions found in extracted data
          {onRetry && (
            <div className="mt-3">
              <button
                type="button"
                onClick={onRetry}
                disabled={retrying}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium bg-amber-100 text-amber-800 hover:bg-amber-200 disabled:opacity-50"
                title="Re-run extraction (e.g. for image-based statements that use OCR)"
              >
                <FaRedo className={retrying ? 'animate-spin' : ''} />
                {retrying ? 'Retrying...' : 'Retry extraction'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const Extracted = () => {
  const { id } = useParams()
  const navigate = useNavigate()
  const [file, setFile] = useState(null)
  const [extraction, setExtraction] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [showPdfModal, setShowPdfModal] = useState(false)
  const [pdfUrl, setPdfUrl] = useState(null)
  const [loadingPdf, setLoadingPdf] = useState(false)
  const [showPayeesSidebar, setShowPayeesSidebar] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [syncMessage, setSyncMessage] = useState('')
  const [workspaceId, setWorkspaceId] = useState(null)
  const [exportingIIF, setExportingIIF] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [showUnmappedModal, setShowUnmappedModal] = useState(false)
  const [unmappedPayees, setUnmappedPayees] = useState([])
  const [unmappedExpenseAccounts, setUnmappedExpenseAccounts] = useState({}) // index -> expense account name
  const [savingMappings, setSavingMappings] = useState(false)
  const [missingPayeeTxns, setMissingPayeeTxns] = useState([]) // transactions with no payee (e.g. checks)
  const [missingPayeeInputs, setMissingPayeeInputs] = useState({}) // index -> { payeeName, expenseAccount }
  // Desktop multi-company: company dropdown at sync time
  const [syncCompanyFile, setSyncCompanyFile] = useState('')
  const [desktopCompanyList, setDesktopCompanyList] = useState([]) // [{ path, name }]
  const [desktopCompanyAccountMap, setDesktopCompanyAccountMap] = useState({})
  const [workspaceQuickbooksAccount, setWorkspaceQuickbooksAccount] = useState('')

  useEffect(() => {
    loadData()
    loadWorkspace()
  }, [id])

  const loadWorkspace = async () => {
    try {
      const workspace = await workspacesAPI.getDefaultWorkspace()
      setWorkspaceId(workspace.id)
      setWorkspaceQuickbooksAccount(workspace.quickbooks_account_name || '')
    } catch (error) {
      console.error('Failed to load workspace:', error)
    }
  }

  // Load desktop QB config for company dropdown (Electron only)
  useEffect(() => {
    if (!isElectron() || !window.electronAPI?.getConfig) return
    window.electronAPI.getConfig().then((config) => {
      if (!config) return
      const map = config.companyAccountMap || {}
      setDesktopCompanyAccountMap(map)
      if (config.companyFilesList && Array.isArray(config.companyFilesList) && config.companyFilesList.length > 0) {
        setDesktopCompanyList(config.companyFilesList)
        if (!syncCompanyFile && config.companyFile) setSyncCompanyFile(config.companyFile)
        else if (!syncCompanyFile && config.companyFilesList[0]?.path) setSyncCompanyFile(config.companyFilesList[0].path)
      } else if (config.companyFile) {
        setDesktopCompanyList([{ path: config.companyFile, name: config.companyFile.split(/[/\\]/).pop() || config.companyFile }])
        if (!syncCompanyFile) setSyncCompanyFile(config.companyFile)
      }
    }).catch(() => {})
  }, [])

  // Clean up blob URL when component unmounts or pdfUrl changes
  useEffect(() => {
    return () => {
      if (pdfUrl) {
        URL.revokeObjectURL(pdfUrl)
      }
    }
  }, [pdfUrl])

  const loadData = async () => {
    try {
      setLoading(true)
      const [fileData, extractionData] = await Promise.all([
        filesAPI.getFile(id),
        extractionAPI.getExtraction(id).catch(() => null),
      ])
      setFile(fileData)
      setExtraction(extractionData)
    } catch (err) {
      setError(err.message || 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async () => {
    if (!window.confirm('Are you sure you want to delete this file? This action cannot be undone.')) {
      return
    }

    try {
      setDeleting(true)
      await filesAPI.deleteFile(id)
      // Navigate to dashboard after successful deletion
      navigate('/dashboard')
    } catch (err) {
      alert(`Failed to delete file: ${err.message}`)
      setDeleting(false)
    }
  }

  const handleCancel = async () => {
    if (!window.confirm('Are you sure you want to stop processing this file? The extraction will be cancelled.')) {
      return
    }

    try {
      setCancelling(true)
      await extractionAPI.cancelExtraction(id)
      // Reload data to show updated status
      await loadData()
      setCancelling(false)
    } catch (err) {
      alert(`Failed to cancel processing: ${err.message}`)
      setCancelling(false)
    }
  }

  const handleRetryExtraction = async () => {
    try {
      setRetrying(true)
      await extractionAPI.retryExtraction(id)
      // Poll until extraction completes or fails
      let attempts = 0
      const maxAttempts = 120 // ~2 min at 1s interval
      while (attempts < maxAttempts) {
        await new Promise((r) => setTimeout(r, 1000))
        const extractionData = await extractionAPI.getExtraction(id).catch(() => null)
        if (extractionData?.extraction_status === 'completed' || extractionData?.extraction_status === 'failed') {
          await loadData()
          break
        }
        attempts += 1
      }
      if (attempts >= maxAttempts) await loadData()
    } catch (err) {
      alert(`Failed to retry extraction: ${err.message}`)
    } finally {
      setRetrying(false)
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
      <div className="space-y-4">
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
        </div>
        <Link to="/dashboard" className="btn-secondary inline-block">
          Back to Dashboard
        </Link>
      </div>
    )
  }

  const loadPdfUrl = async () => {
    if (pdfUrl) return pdfUrl // Already loaded
    
    setLoadingPdf(true)
    try {
      // Use API_BASE_URL imported from api.js
      const token = localStorage.getItem('access_token')
      
      const response = await fetch(`${API_BASE_URL}/files/${id}/download`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
      
      if (!response.ok) {
        throw new Error('Failed to load PDF')
      }
      
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      setPdfUrl(url)
      return url
    } catch (error) {
      console.error('Failed to load PDF:', error)
      alert('Failed to load PDF file')
    } finally {
      setLoadingPdf(false)
    }
  }

  const handleOpenPdfModal = async () => {
    await loadPdfUrl()
    setShowPdfModal(true)
  }

  const handleClosePdfModal = () => {
    setShowPdfModal(false)
    // Optionally clean up blob URL when closing
    // if (pdfUrl) {
    //   URL.revokeObjectURL(pdfUrl)
    //   setPdfUrl(null)
    // }
  }

  const handleExportIIF = async () => {
    if (!workspaceId) {
      setSyncMessage('Error: Workspace not loaded')
      return
    }

    setExportingIIF(true)
    setSyncMessage('')

    try {
      // Export only from the current file (id from URL params)
      await qbQueueAPI.exportToIIF(workspaceId, id ? parseInt(id) : null, 1000)
      setSyncMessage('Success! IIF file downloaded with transactions from this statement. Import into QuickBooks Desktop via File → Utilities → Import → IIF Files.')
    } catch (error) {
      console.error('Failed to export IIF:', error)
      setSyncMessage(`Error: ${error.message || 'Failed to export IIF file'}`)
    } finally {
      setExportingIIF(false)
    }
  }

  const handleSyncToQuickBooks = async (skipIndices = new Set()) => {
    if (!workspaceId) {
      setSyncMessage('Error: Workspace not loaded')
      return
    }

    if (!extraction?.processed_data?.transactions || extraction.processed_data.transactions.length === 0) {
      setSyncMessage('No transactions to sync')
      return
    }

    // Desktop multi-company: require company selection and account for that company
    if (isElectron() && desktopCompanyList.length > 0) {
      if (!syncCompanyFile) {
        setSyncMessage('Select a QuickBooks company to sync to.')
        return
      }
      const accountForCompany = (desktopCompanyAccountMap[syncCompanyFile] || '').trim()
      const fallbackAccount = workspaceQuickbooksAccount || (extraction?.processed_data?.account_name || 'Checking')
      if (!accountForCompany && !fallbackAccount) {
        setSyncMessage('Set the QuickBooks account for this company in Settings (QuickBooks SDK Sync) before syncing.')
        return
      }
    }

    setSyncing(true)
    setSyncMessage('')

    try {
      // Check for unmapped payees and missing-payee transactions before queueing
      // Pass local transactions (which may have user-entered payee names) instead of file IDs
      const localTxns = (extraction.processed_data.transactions || []).map((t, i) => ({
        ...t, _file_id: parseInt(id), _transaction_index: i
      }))
      const checkRes = await qbQueueAPI.checkUnmappedPayees(workspaceId, {
        transactionList: localTxns
      })
      // Filter out transactions the user chose to skip
      const effectiveMissing = (checkRes.missing_payee_transactions || []).filter(
        t => !skipIndices.has(t.transaction_index)
      )
      if ((checkRes.unmapped_payees?.length > 0) || effectiveMissing.length > 0) {
        setUnmappedPayees(checkRes.unmapped_payees || [])
        setUnmappedExpenseAccounts({})
        setMissingPayeeTxns(effectiveMissing)
        setMissingPayeeInputs({})
        setSyncMessage('')
        setShowUnmappedModal(true)
        setSyncing(false)
        return
      }

      const transactions = extraction.processed_data.transactions
      const queueIds = []
      let skippedCount = 0
      const companyFileToSend = (isElectron() && desktopCompanyList.length > 0 && syncCompanyFile) ? syncCompanyFile : null

      // Queue each transaction (skip indices the user chose to skip)
      for (let i = 0; i < transactions.length; i++) {
        if (skipIndices.has(i)) { skippedCount++; continue }
        const trans = transactions[i]
        try {
          const result = await qbQueueAPI.queueTransaction(
            workspaceId,
            parseInt(id),
            {
              ...trans,
              account: extraction.processed_data.account_name || 'Checking',
              transaction_type: trans.transaction_type || (trans.amount >= 0 ? 'DEPOSIT' : 'WITHDRAWAL')
            },
            i,
            trans.transaction_id || `trans-${id}-${i}`,
            companyFileToSend
          )
          queueIds.push(result.id)
        } catch (error) {
          console.error(`Failed to queue transaction ${i}:`, error)
          if (error?.detail?.code === 'unmapped_payee' || (error?.message && /payee|expense account|map/i.test(error.message))) {
            setSyncMessage(error.message || 'One or more payees need a QuickBooks expense account. Go to Payees to set it, then try Sync again.')
            setSyncing(false)
            return
          }
          // Continue with other transactions for other errors
        }
      }

      if (queueIds.length === 0) {
        setSyncMessage(skippedCount > 0 ? `No transactions were queued (${skippedCount} skipped).` : 'Error: No transactions were queued')
        setSyncing(false)
        return
      }

      const skippedNote = skippedCount > 0 ? ` (${skippedCount} check(s) without payees skipped)` : ''

      // Auto-approve all queued transactions (since extraction is already reviewed)
      try {
        await qbQueueAPI.approveTransactions(workspaceId, queueIds)
        
        // If running in SDK desktop app, trigger immediate sync
        if (isElectron() && window.electronAPI?.triggerSyncCheck) {
          try {
            await electronAPI.triggerSyncCheck()
            setSyncMessage(`Success! ${queueIds.length} transaction(s) queued and approved.${skippedNote} Sync service is starting...`)
          } catch (syncError) {
            console.error('Failed to trigger sync:', syncError)
            setSyncMessage(`Success! ${queueIds.length} transaction(s) queued and approved.${skippedNote} Sync will start automatically.`)
          }
        } else {
          setSyncMessage(`Success! ${queueIds.length} transaction(s) queued and approved for QuickBooks sync.${skippedNote} They will be synced automatically.`)
        }
      } catch (error) {
        console.error('Failed to approve transactions:', error)
        setSyncMessage(`Warning: ${queueIds.length} transaction(s) queued but approval failed. You can approve them manually from the queue.`)
      }
    } catch (error) {
      console.error('Failed to sync to QuickBooks:', error)
      setSyncMessage(`Error: ${error.message || 'Failed to sync transactions'}`)
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Extraction Results</h1>
          <p className="text-sm text-gray-500 mt-1">{file?.original_filename}</p>
        </div>
        <div className="flex gap-3">
          <Button
            onClick={() => setShowPayeesSidebar(true)}
            variant="secondary"
            className="text-sm flex items-center"
          >
            <FaUsers className="mr-2" />
            Suggested Payees
          </Button>
          {/* View PDF Button - Only show for PDF files */}
          {file?.file_type?.toLowerCase() === 'pdf' && (
            <button
              onClick={handleOpenPdfModal}
              disabled={loadingPdf}
              className="px-4 py-2 rounded-lg font-medium transition-colors duration-200 bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              title="View PDF"
            >
              <FaFilePdf className="text-base" />
              {loadingPdf ? 'Loading...' : 'View PDF'}
            </button>
          )}
          {file?.status === 'processing' && (
            <button
              onClick={handleCancel}
              disabled={cancelling}
              className="px-3 py-2 rounded-lg font-medium transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed bg-gray-200 text-gray-800 hover:bg-gray-300 flex items-center justify-center"
              title={cancelling ? 'Cancelling...' : 'Stop Processing'}
            >
              <FaTimes className="text-base" />
            </button>
          )}
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="px-3 py-2 rounded-lg font-medium transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed bg-red-600 text-white hover:bg-red-700 flex items-center justify-center"
            title={deleting ? 'Deleting...' : 'Delete File'}
          >
            <FaTrash className="text-base" />
          </button>
          <Link to="/dashboard" className="btn-secondary">
            Back
          </Link>
        </div>
      </div>

      {/* File Information - Horizontal Layout (Full Width) */}
      <Card>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 md:gap-6">
          <div>
            <p className="text-xs font-medium text-gray-500 mb-1">File Name</p>
            <p className="text-sm font-semibold text-gray-900 truncate" title={file?.original_filename}>
              {file?.original_filename}
            </p>
          </div>
          <div>
            <p className="text-xs font-medium text-gray-500 mb-1">File Type</p>
            <p className="text-sm font-semibold text-gray-900 uppercase">{file?.file_type}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-gray-500 mb-1">Status</p>
            <span
              className={`inline-block px-3 py-1 text-xs font-semibold rounded-full ${
                file?.status === 'completed'
                  ? 'bg-green-100 text-green-800'
                  : file?.status === 'processing'
                  ? 'bg-yellow-100 text-yellow-800'
                  : file?.status === 'failed'
                  ? 'bg-red-100 text-red-800'
                  : 'bg-gray-100 text-gray-800'
              }`}
            >
              {file?.status}
            </span>
          </div>
          <div>
            <p className="text-xs font-medium text-gray-500 mb-1">Uploaded</p>
            <p className="text-sm font-semibold text-gray-900">
              {file?.created_at ? new Date(file.created_at).toLocaleDateString() : 'N/A'}
            </p>
          </div>
        </div>
      </Card>

      {/* Extracted Data - Full Width */}
      <Card title="Extracted Data">
        {!extraction ? (
          <div className="text-center py-8">
            <p className="text-gray-500">No extraction data available yet</p>
            <p className="text-sm text-gray-400 mt-2">
              Extraction may still be processing...
            </p>
          </div>
        ) : extraction.extraction_status === 'failed' ? (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-sm font-medium text-red-800">Extraction Failed</p>
            <p className="text-sm text-red-600 mt-1">{extraction.error_message || 'Unknown error'}</p>
          </div>
        ) : extraction.extraction_status === 'pending' ? (
          <div className="text-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
            <p className="text-gray-500">Processing extraction...</p>
          </div>
          ) : (
            <div className="space-y-4">
              {extraction.processed_data ? (
                (() => {
                  const data = extraction.processed_data
                  // Determine document type more intelligently
                  // Bank statement indicators: transactions array, bank_name, statement_period
                  const isBankStatement = (
                    data.document_type === 'bank_statement' ||
                    data.document_type === 'multi_check' ||
                    (data.transactions && Array.isArray(data.transactions) && data.transactions.length > 0) ||
                    (data.bank_name && !data.check_number) ||
                    data.statement_period_start ||
                    data.statement_period_end ||
                    (data.beginning_balance !== undefined && data.beginning_balance !== null) ||
                    (data.ending_balance !== undefined && data.ending_balance !== null)
                  )
                  
                  // Check indicators: check_number, payee without transactions
                  const isCheck = (
                    data.document_type === 'check' ||
                    (data.check_number && !isBankStatement) ||
                    (data.payee && !data.transactions && !isBankStatement && !data.bank_name)
                  )
                  
                  // Show appropriate display
                  if (isCheck && !isBankStatement) {
                    return <CheckDisplay data={data} />
                  } else if (isBankStatement) {
                    return <BankStatementDisplay data={data} onRetry={handleRetryExtraction} retrying={retrying} />
                  } else if (data.raw_text) {
                    // Fallback: show raw text if available
                    return (
                      <div className="space-y-4">
                        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                          <p className="text-sm font-medium text-yellow-800">Unstructured Document</p>
                          <p className="text-sm text-yellow-600 mt-1">
                            This document could not be automatically classified. Showing raw extracted text.
                          </p>
                        </div>
                        <details className="bg-gray-50 rounded-lg p-4">
                          <summary className="text-sm font-semibold text-gray-900 cursor-pointer hover:text-gray-700">
                            View Raw Extracted Text
                          </summary>
                          <pre className="mt-3 text-xs text-gray-600 whitespace-pre-wrap max-h-96 overflow-y-auto">
                            {data.raw_text}
                          </pre>
                        </details>
                      </div>
                    )
                  } else {
                    return (
                      <div className="text-center py-8">
                        <p className="text-gray-500">No extractable data found</p>
                        <p className="text-sm text-gray-400 mt-2">
                          The document may not contain recognizable check or bank statement data.
                        </p>
                      </div>
                    )
                  }
                })()
              ) : (
                <div className="text-center py-8">
                  <p className="text-gray-500">Processing extraction data...</p>
                </div>
              )}
            </div>
          )}
      </Card>

      {/* Export Options */}
      {extraction?.extraction_status === 'completed' && extraction?.processed_data?.transactions?.length > 0 && (
        <Card title="QuickBooks Sync">
          <div className="space-y-4">
            {isElectron() && desktopCompanyList.length > 0 && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Sync to company</label>
                <select
                  value={syncCompanyFile}
                  onChange={(e) => setSyncCompanyFile(e.target.value)}
                  className="w-full max-w-md px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  {desktopCompanyList.map((f) => (
                    <option key={f.path} value={f.path}>
                      {f.name || f.path}
                    </option>
                  ))}
                </select>
                {syncCompanyFile && !(desktopCompanyAccountMap[syncCompanyFile] || '').trim() && !workspaceQuickbooksAccount && (
                  <p className="mt-1 text-xs text-amber-600">
                    Set the QuickBooks account for this company in Settings → QuickBooks SDK Sync.
                  </p>
                )}
              </div>
            )}
            <div className="flex flex-wrap gap-3">
              <Button
                onClick={() => handleSyncToQuickBooks()}
                disabled={syncing || !workspaceId}
                variant="primary"
                className="flex items-center gap-2"
              >
                <FaSync className={syncing ? 'animate-spin' : ''} />
                {syncing ? 'Syncing...' : 'Sync to QuickBooks'}
              </Button>
              {workspaceId && (
                <button
                  onClick={handleExportIIF}
                  disabled={exportingIIF}
                  className="px-4 py-2 rounded-lg font-medium transition-colors duration-200 bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                  title="Export all queued transactions to IIF file"
                >
                  <FaDownload className={exportingIIF ? 'animate-pulse' : ''} />
                  {exportingIIF ? 'Exporting...' : 'Export Queued Transactions (.IIF)'}
                </button>
              )}
            </div>
            {syncMessage && (
              <div
                className={`p-3 rounded-lg ${
                  syncMessage.includes('Success') || syncMessage.includes('queued')
                    ? 'bg-green-50 text-green-700 border border-green-200'
                    : syncMessage.includes('Warning')
                    ? 'bg-yellow-50 text-yellow-700 border border-yellow-200'
                    : 'bg-red-50 text-red-700 border border-red-200'
                }`}
              >
                {syncMessage}
              </div>
            )}
            <p className="text-sm text-gray-500">
              <strong>Sync to QuickBooks:</strong> Automatically syncs all transactions to QuickBooks Desktop via QB Web Connector (syncs within 5 minutes).
              <br />
              <strong>Export Queued Transactions (.IIF):</strong> Download IIF file for transactions from this statement only (works for both checks and bank statements). Uses the workspace's configured QuickBooks account. Import into QuickBooks Desktop via File → Utilities → Import → IIF Files.
            </p>
          </div>
        </Card>
      )}

      {/* Raw Data (if available) - Collapsible */}
      {extraction?.raw_data && Object.keys(extraction.raw_data).length > 0 && (
        <Card title="Raw Extraction Data">
          <details className="cursor-pointer">
            <summary className="text-sm text-gray-600 hover:text-gray-900">
              Click to view raw JSON data
            </summary>
            <pre className="bg-gray-50 p-4 rounded-lg overflow-x-auto text-xs mt-2">
              {JSON.stringify(extraction.raw_data, null, 2)}
            </pre>
          </details>
        </Card>
      )}

      {/* Unmapped Payees Modal - block Sync to QB until payees have QB expense account */}
      {showUnmappedModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 overflow-y-auto py-8">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 p-6 my-8">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">Map these payees</h3>
              <button
                onClick={() => { setShowUnmappedModal(false); setUnmappedPayees([]); setUnmappedExpenseAccounts({}); setMissingPayeeTxns([]); setMissingPayeeInputs({}) }}
                className="text-gray-500 hover:text-gray-700"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4 mb-6 max-h-[50vh] overflow-y-auto">
              {/* Section 1: Transactions with no payee (e.g. checks from bank statements) */}
              {missingPayeeTxns.length > 0 && (
                <div>
                  <p className="text-sm text-gray-600 mb-3">
                    These transactions have no payee. Enter the payee name and QuickBooks expense account for each.
                  </p>
                  {missingPayeeTxns.map((t, i) => (
                    <div key={`missing-${i}`} className="flex flex-col gap-1.5 p-3 bg-amber-50 rounded-lg mb-3 border border-amber-200">
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-amber-900">{t.description || `${t.transaction_type} transaction`}</span>
                        <span className="text-sm text-amber-700 font-mono">${Number(t.amount || 0).toFixed(2)}</span>
                      </div>
                      <Input
                        value={missingPayeeInputs[i]?.payeeName ?? ''}
                        onChange={(e) => setMissingPayeeInputs(prev => ({ ...prev, [i]: { ...prev[i], payeeName: e.target.value } }))}
                        placeholder="Enter payee name (e.g. John Smith, ABC Corp)"
                        className="mb-0"
                      />
                      <Input
                        value={missingPayeeInputs[i]?.expenseAccount ?? ''}
                        onChange={(e) => setMissingPayeeInputs(prev => ({ ...prev, [i]: { ...prev[i], expenseAccount: e.target.value } }))}
                        placeholder="Expense account (e.g. Rent Expense, Utilities)"
                        className="mb-0"
                      />
                    </div>
                  ))}
                </div>
              )}

              {/* Section 2: Existing payees without expense accounts (existing behavior) */}
              {unmappedPayees.length > 0 && (
                <div>
                  {missingPayeeTxns.length > 0 && <hr className="my-3 border-gray-200" />}
                  <p className="text-sm text-gray-600 mb-3">
                    Set a QuickBooks expense account for each payee. Must match an account in your QuickBooks Chart of Accounts.
                  </p>
                  {unmappedPayees.map((p, i) => (
                    <div key={`unmapped-${i}`} className="flex flex-col gap-1 p-3 bg-gray-50 rounded-lg mb-3">
                      <span className="text-sm font-medium text-gray-800">{p.payee_name}</span>
                      <Input
                        value={unmappedExpenseAccounts[i] ?? ''}
                        onChange={(e) => setUnmappedExpenseAccounts(prev => ({ ...prev, [i]: e.target.value }))}
                        placeholder="e.g. Rent Expense, Utilities"
                        className="mb-0"
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                variant="primary"
                onClick={async () => {
                  if (!workspaceId) return
                  setSavingMappings(true)
                  try {
                    let saved = 0

                    // Save missing-payee transactions: create payee + set expense account + update local extraction
                    for (let i = 0; i < missingPayeeTxns.length; i++) {
                      const input = missingPayeeInputs[i] || {}
                      const payeeName = (input.payeeName ?? '').trim()
                      const expenseAccount = (input.expenseAccount ?? '').trim()
                      if (!payeeName || !expenseAccount) continue
                      const created = await payeeManagementAPI.createPayee(workspaceId, payeeName, false)
                      if (created?.id) {
                        await payeeManagementAPI.updatePayee(workspaceId, created.id, { qb_expense_account_name: expenseAccount })
                        saved++
                      }
                      // Update local extraction data so the payee name is used when queueing
                      const txIdx = missingPayeeTxns[i].transaction_index
                      if (extraction?.processed_data?.transactions?.[txIdx] != null) {
                        setExtraction(prev => {
                          const updated = { ...prev, processed_data: { ...prev.processed_data, transactions: [...prev.processed_data.transactions] } }
                          updated.processed_data.transactions[txIdx] = { ...updated.processed_data.transactions[txIdx], payee: payeeName }
                          return updated
                        })
                      }
                    }

                    // Save unmapped payees with expense accounts (existing behavior)
                    for (let i = 0; i < unmappedPayees.length; i++) {
                      const value = (unmappedExpenseAccounts[i] ?? '').trim()
                      if (!value) continue
                      const p = unmappedPayees[i]
                      let payeeId = p.payee_id
                      if (!payeeId) {
                        const created = await payeeManagementAPI.createPayee(workspaceId, p.payee_name, false)
                        payeeId = created?.id
                      }
                      if (payeeId) {
                        await payeeManagementAPI.updatePayee(workspaceId, payeeId, { qb_expense_account_name: value })
                        saved++
                      }
                    }

                    // Determine which missing-payee txns the user has NOT yet filled in
                    const remainingMissing = missingPayeeTxns.filter((_, idx) => {
                      const inp = missingPayeeInputs[idx] || {}
                      return !((inp.payeeName ?? '').trim() && (inp.expenseAccount ?? '').trim())
                    })
                    // Re-check backend using local transactions (which now have updated payee names)
                    const recheckTxns = (extraction?.processed_data?.transactions || []).map((t, idx) => ({
                      ...t, _file_id: parseInt(id), _transaction_index: idx
                    }))
                    const checkRes = await qbQueueAPI.checkUnmappedPayees(workspaceId, { transactionList: recheckTxns })
                    const stillUnmapped = checkRes.unmapped_payees || []
                    if (stillUnmapped.length === 0 && remainingMissing.length === 0) {
                      setShowUnmappedModal(false)
                      setUnmappedPayees([])
                      setUnmappedExpenseAccounts({})
                      setMissingPayeeTxns([])
                      setMissingPayeeInputs({})
                      setSyncMessage(saved ? `Mappings saved. All payees are mapped. You can now sync to QuickBooks.` : '')
                    } else {
                      setUnmappedPayees(stillUnmapped)
                      setUnmappedExpenseAccounts({})
                      setMissingPayeeTxns(remainingMissing)
                      setMissingPayeeInputs({})
                      setSyncMessage(saved ? `Saved ${saved} mapping(s). Fill in the remaining payees below.` : '')
                    }
                  } catch (err) {
                    console.error('Failed to save payee mappings:', err)
                    setSyncMessage(`Error: ${err?.message || 'Failed to save mappings'}`)
                  } finally {
                    setSavingMappings(false)
                  }
                }}
                disabled={savingMappings || (
                  !Object.values(unmappedExpenseAccounts).some(v => (v ?? '').trim()) &&
                  !Object.values(missingPayeeInputs).some(v => (v?.payeeName ?? '').trim() && (v?.expenseAccount ?? '').trim())
                )}
              >
                {savingMappings ? 'Saving...' : 'Save mappings'}
              </Button>
              {missingPayeeTxns.length > 0 && unmappedPayees.length === 0 && (
                <Button
                  variant="secondary"
                  onClick={() => {
                    const skip = new Set(missingPayeeTxns.map(t => t.transaction_index))
                    setShowUnmappedModal(false)
                    setUnmappedPayees([])
                    setUnmappedExpenseAccounts({})
                    setMissingPayeeTxns([])
                    setMissingPayeeInputs({})
                    handleSyncToQuickBooks(skip)
                  }}
                  disabled={savingMappings}
                >
                  Skip these & sync rest ({extraction?.processed_data?.transactions
                    ? extraction.processed_data.transactions.length - missingPayeeTxns.length
                    : '?'} transactions)
                </Button>
              )}
              <Link
                to="/payees"
                className="inline-flex items-center justify-center px-4 py-2 rounded-lg font-medium border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
              >
                Go to Payees
              </Link>
              <Button
                variant="secondary"
                onClick={() => { setShowUnmappedModal(false); setUnmappedPayees([]); setUnmappedExpenseAccounts({}); setMissingPayeeTxns([]); setMissingPayeeInputs({}) }}
                disabled={savingMappings}
              >
                Close
              </Button>
            </div>
            {syncMessage && showUnmappedModal && (
              <p className={`mt-3 text-sm ${syncMessage.startsWith('Error') ? 'text-red-600' : 'text-green-700'}`}>
                {syncMessage}
              </p>
            )}
          </div>
        </div>
      )}

      {/* PDF Viewer Modal */}
      {showPdfModal && file?.file_type?.toLowerCase() === 'pdf' && (
        <div className="fixed inset-0 z-50 overflow-y-auto" aria-labelledby="modal-title" role="dialog" aria-modal="true">
          {/* Backdrop */}
          <div 
            className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"
            onClick={() => setShowPdfModal(false)}
          ></div>

          {/* Modal */}
          <div className="flex min-h-full items-center justify-center p-4">
            <div className="relative transform overflow-hidden rounded-lg bg-white shadow-xl transition-all w-full max-w-6xl max-h-[90vh] flex flex-col">
              {/* Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
                <div className="flex items-center gap-3">
                  <FaFilePdf className="text-red-600 text-xl" />
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900">{file.original_filename}</h3>
                    <p className="text-sm text-gray-500">PDF Viewer</p>
                  </div>
                </div>
                <button
                  onClick={() => setShowPdfModal(false)}
                  className="text-gray-400 hover:text-gray-600 transition-colors"
                  title="Close"
                >
                  <FaTimesCircle className="text-2xl" />
                </button>
              </div>

              {/* PDF Content */}
              <div className="flex-1 overflow-hidden bg-gray-100">
                {loadingPdf ? (
                  <div className="flex items-center justify-center h-full">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
                  </div>
                ) : pdfUrl ? (
                  <iframe
                    src={pdfUrl}
                    className="w-full h-full border-0"
                    title="PDF Viewer"
                    style={{ minHeight: '600px' }}
                  ></iframe>
                ) : (
                  <div className="flex items-center justify-center h-full text-gray-500">
                    Failed to load PDF
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="px-6 py-3 border-t border-gray-200 bg-gray-50">
                <div className="flex items-center justify-between">
                  <p className="text-sm text-gray-500">
                    {file.file_size ? `${(file.file_size / 1024).toFixed(2)} KB` : ''}
                  </p>
                  <div className="flex gap-2">
                    {pdfUrl && (
                      <a
                        href={pdfUrl}
                        download={file.original_filename}
                        className="px-4 py-2 text-sm font-medium text-blue-600 hover:text-blue-800"
                      >
                        Download
                      </a>
                    )}
                    <button
                      onClick={handleClosePdfModal}
                      className="px-4 py-2 text-sm font-medium text-gray-700 hover:text-gray-900"
                    >
                      Close
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Suggested Payees Sidebar */}
      <SuggestedPayeesSidebar
        isOpen={showPayeesSidebar}
        onClose={() => setShowPayeesSidebar(false)}
        onSelectPayee={(payee) => {
          // Handle payee selection - could update the extracted data
          console.log('Selected payee:', payee)
        }}
        currentPayeeName={
          extraction?.raw_data?.payee || 
          extraction?.processed_data?.payee ||
          (extraction?.raw_data?.transactions?.[0]?.payee)
        }
      />
    </div>
  )
}

export default Extracted

