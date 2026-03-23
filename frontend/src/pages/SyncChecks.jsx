import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { filesAPI, extractionAPI, workspacesAPI, qbQueueAPI, payeeManagementAPI } from '../utils/api'
import { isElectron, electronAPI } from '../utils/electron-api'
import Card from '../components/Card'
import Button from '../components/Button'
import Input from '../components/Input'
import { FaSync, FaCheckSquare, FaSquare, FaEye } from 'react-icons/fa'

const SyncChecks = () => {
  const navigate = useNavigate()
  const [workspaceId, setWorkspaceId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [filesWithStatus, setFilesWithStatus] = useState([]) // { file, extraction, synced }
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [syncing, setSyncing] = useState(false)
  const [message, setMessage] = useState('')
  const [messageType, setMessageType] = useState('') // 'success' | 'error' | 'warning'
  const [showUnmappedModal, setShowUnmappedModal] = useState(false)
  const [unmappedPayees, setUnmappedPayees] = useState([])
  const [unmappedExpenseAccounts, setUnmappedExpenseAccounts] = useState({})
  const [missingPayeeTxns, setMissingPayeeTxns] = useState([])
  const [missingPayeeInputs, setMissingPayeeInputs] = useState({})
  const [savingMappings, setSavingMappings] = useState(false)
  const [syncCompanyFile, setSyncCompanyFile] = useState('')
  const [desktopCompanyList, setDesktopCompanyList] = useState([])
  const [desktopCompanyAccountMap, setDesktopCompanyAccountMap] = useState({})
  const [workspaceQuickbooksAccount, setWorkspaceQuickbooksAccount] = useState('')

  useEffect(() => {
    const load = async () => {
      try {
        const workspace = await workspacesAPI.getDefaultWorkspace()
        setWorkspaceId(workspace.id)
        setWorkspaceQuickbooksAccount(workspace.quickbooks_account_name || '')
      } catch (e) {
        console.error('Failed to load workspace:', e)
        setWorkspaceId(1)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  useEffect(() => {
    if (!isElectron() || !window.electronAPI?.getConfig) return
    window.electronAPI.getConfig().then((config) => {
      if (!config) return
      setDesktopCompanyAccountMap(config.companyAccountMap || {})
      if (config.companyFilesList?.length > 0) {
        setDesktopCompanyList(config.companyFilesList)
        if (!syncCompanyFile) setSyncCompanyFile(config.companyFile || config.companyFilesList[0]?.path || '')
      } else if (config.companyFile) {
        setDesktopCompanyList([{ path: config.companyFile, name: config.companyFile.split(/[/\\]/).pop() || config.companyFile }])
        if (!syncCompanyFile) setSyncCompanyFile(config.companyFile)
      }
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!workspaceId) return

    const loadSingleChecks = async () => {
      setLoading(true)
      setMessage('')
      try {
        const files = await filesAPI.listFiles(workspaceId)
        const singleChecks = (files || []).filter(
          (f) => f.document_type === 'individual_check' && f.status === 'completed'
        )
        if (singleChecks.length === 0) {
          setFilesWithStatus([])
          setLoading(false)
          return
        }

        const queueRes = await qbQueueAPI.listQueue(workspaceId, null, 500)
        const queueEntries = queueRes?.transactions || []
        const syncedCountByFileId = {}
        queueEntries.forEach((entry) => {
          if (entry.status === 'synced' && entry.file_id) {
            syncedCountByFileId[entry.file_id] = (syncedCountByFileId[entry.file_id] || 0) + 1
          }
        })

        const withStatus = []
        for (const file of singleChecks) {
          let extraction = null
          try {
            extraction = await extractionAPI.getExtraction(file.id)
          } catch (e) {
            console.warn(`No extraction for file ${file.id}:`, e)
          }
          const transactions = extraction?.processed_data?.transactions || []
          const txCount = transactions.length
          const syncedCount = syncedCountByFileId[file.id] || 0
          const synced = txCount > 0 && syncedCount >= txCount
          withStatus.push({ file, extraction, synced, txCount })
        }
        setFilesWithStatus(withStatus)
      } catch (e) {
        console.error('Failed to load single checks:', e)
        setMessage('Failed to load single checks')
        setMessageType('error')
      } finally {
        setLoading(false)
      }
    }

    loadSingleChecks()
  }, [workspaceId])

  const notSyncedFiles = useMemo(
    () => filesWithStatus.filter(({ synced }) => !synced),
    [filesWithStatus]
  )
  const notSyncedIds = useMemo(() => new Set(notSyncedFiles.map(({ file }) => file.id)), [notSyncedFiles])

  const handleSelect = (fileId) => {
    if (!notSyncedIds.has(fileId)) return
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(fileId)) next.delete(fileId)
      else next.add(fileId)
      return next
    })
  }

  const handleSelectAll = () => {
    if (selectedIds.size === notSyncedIds.size) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(notSyncedIds))
    }
  }

  const handleSyncSelected = async (skipKeys = new Set()) => {
    if (!workspaceId || selectedIds.size === 0) {
      setMessage('Select one or more checks to sync')
      setMessageType('error')
      return
    }

    if (isElectron() && desktopCompanyList.length > 0) {
      if (!syncCompanyFile) {
        setMessage('Select a QuickBooks company to sync to.')
        setMessageType('error')
        return
      }
      const accountForCompany = (desktopCompanyAccountMap[syncCompanyFile] || '').trim()
      if (!accountForCompany && !workspaceQuickbooksAccount) {
        setMessage('Set the QuickBooks account for this company in Settings (QuickBooks SDK Sync) before syncing.')
        setMessageType('error')
        return
      }
    }

    // Pass local transactions (which may have user-entered payee names) instead of file IDs
    const allLocalTxns = []
    for (const { file, extraction } of filesWithStatus) {
      if (!selectedIds.has(file.id)) continue
      const txns = extraction?.processed_data?.transactions || []
      txns.forEach((t, i) => allLocalTxns.push({ ...t, _file_id: file.id, _transaction_index: i }))
    }
    const checkRes = await qbQueueAPI.checkUnmappedPayees(workspaceId, {
      transactionList: allLocalTxns,
    })
    const effectiveMissing = (checkRes.missing_payee_transactions || []).filter(
      t => !skipKeys.has(`${t.file_id}-${t.transaction_index}`)
    )
    if ((checkRes.unmapped_payees?.length > 0) || effectiveMissing.length > 0) {
      setUnmappedPayees(checkRes.unmapped_payees || [])
      setUnmappedExpenseAccounts({})
      setMissingPayeeTxns(effectiveMissing)
      setMissingPayeeInputs({})
      setShowUnmappedModal(true)
      setMessage('')
      return
    }

    setSyncing(true)
    setMessage('')

    let skippedCount = 0
    const queueIds = []
    const companyFileToSend = (isElectron() && desktopCompanyList.length > 0 && syncCompanyFile) ? syncCompanyFile : null
    const getTransactionsForFile = (extraction) => {
      const pd = extraction?.processed_data
      if (!pd) return []
      if (pd.transactions && Array.isArray(pd.transactions) && pd.transactions.length > 0) {
        return pd.transactions
      }
      // Single-check shape: payee, amount, date at top level (backend may not have normalized yet)
      if (pd.payee != null || (pd.amount != null && pd.document_type === 'check')) {
        const amount = pd.amount != null ? Number(pd.amount) : 0
        return [
          {
            date: pd.date || '',
            amount,
            description: `Check #${pd.check_number || ''}`.trim(),
            payee: (pd.payee || '').trim() || 'Unknown',
            transaction_type: 'WITHDRAWAL',
            reference_number: pd.check_number,
            check_number: pd.check_number,
            memo: pd.memo,
          },
        ]
      }
      return []
    }

    try {
      for (const { file, extraction } of filesWithStatus) {
        if (!selectedIds.has(file.id) || !extraction?.processed_data) continue
        const transactions = getTransactionsForFile(extraction)
        if (transactions.length === 0) continue
        const account = extraction.processed_data.account_name || 'Checking'
        for (let i = 0; i < transactions.length; i++) {
          if (skipKeys.has(`${file.id}-${i}`)) { skippedCount++; continue }
          const trans = transactions[i]
          try {
            const result = await qbQueueAPI.queueTransaction(
              workspaceId,
              file.id,
              {
                ...trans,
                account,
                transaction_type: trans.transaction_type || (trans.amount >= 0 ? 'DEPOSIT' : 'WITHDRAWAL'),
              },
              i,
              trans.transaction_id || `trans-${file.id}-${i}`,
              companyFileToSend
            )
            queueIds.push(result.id)
          } catch (err) {
            console.error(`Queue failed for file ${file.id} tx ${i}:`, err)
            const msg = err?.message || err?.detail || String(err)
            if (/payee|expense account|map/i.test(msg)) {
              setMessage(msg || 'One or more payees need a QuickBooks expense account. Set it in Payees, then try again.')
              setMessageType('error')
              setSyncing(false)
              return
            }
            setMessage(msg || 'Failed to queue a transaction. See console for details.')
            setMessageType('error')
            setSyncing(false)
            return
          }
        }
      }

      if (queueIds.length === 0) {
        setMessage('No transactions were queued. Extracted data may have no transactions for the selected files.')
        setMessageType('error')
        setSyncing(false)
        return
      }

      await qbQueueAPI.approveTransactions(workspaceId, queueIds)
      if (isElectron() && window.electronAPI?.triggerSyncCheck) {
        try {
          await electronAPI.triggerSyncCheck()
        } catch (_) {}
      }
      const skippedNote = skippedCount > 0 ? ` (${skippedCount} check(s) without payees skipped)` : ''
      setMessage(`Success! ${queueIds.length} transaction(s) queued and approved for QuickBooks sync.${skippedNote}`)
      setMessageType('success')
      setSelectedIds(new Set())
      setShowUnmappedModal(false)
      setUnmappedPayees([])
      // Reload to refresh synced status
      const files = await filesAPI.listFiles(workspaceId)
      const singleChecks = (files || []).filter(
        (f) => f.document_type === 'individual_check' && f.status === 'completed'
      )
      const queueRes = await qbQueueAPI.listQueue(workspaceId, null, 500)
      const queueEntries = queueRes?.transactions || []
      const syncedCountByFileId = {}
      queueEntries.forEach((entry) => {
        if (entry.status === 'synced' && entry.file_id) {
          syncedCountByFileId[entry.file_id] = (syncedCountByFileId[entry.file_id] || 0) + 1
        }
      })
      const withStatus = []
      for (const file of singleChecks) {
        let extraction = null
        try {
          extraction = await extractionAPI.getExtraction(file.id)
        } catch (_) {}
        const transactions = extraction?.processed_data?.transactions || []
        const txCount = transactions.length
        const syncedCount = syncedCountByFileId[file.id] || 0
        const synced = txCount > 0 && syncedCount >= txCount
        withStatus.push({ file, extraction, synced, txCount })
      }
      setFilesWithStatus(withStatus)
    } catch (err) {
      console.error('Sync failed:', err)
      setMessage(err?.message || 'Failed to sync to QuickBooks')
      setMessageType('error')
    } finally {
      setSyncing(false)
    }
  }

  if (loading && filesWithStatus.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">Sync Single Checks to QuickBooks</h1>
      <p className="text-sm text-gray-600">
        Only completed single-check files are listed. Select checks that are not yet synced and sync them in one go.
      </p>

      <Card>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-4">
          <div>
            <p className="text-sm text-gray-500">
              {filesWithStatus.length} single check(s) • {notSyncedFiles.length} not synced
            </p>
            {notSyncedFiles.length > 0 && selectedIds.size === 0 && (
              <p className="text-xs text-gray-500 mt-1">
                Select one or more checks below, then click Sync.
              </p>
            )}
          </div>
          {notSyncedFiles.length > 0 && (
            <div className="flex flex-wrap items-center gap-3">
              {isElectron() && desktopCompanyList.length > 0 && (
                <div className="w-full sm:w-auto">
                  <label className="block text-xs font-medium text-gray-500 mb-1">Sync to company</label>
                  <select
                    value={syncCompanyFile}
                    onChange={(e) => setSyncCompanyFile(e.target.value)}
                    className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 min-w-[200px]"
                  >
                    {desktopCompanyList.map((f) => (
                      <option key={f.path} value={f.path}>
                        {f.name || f.path}
                      </option>
                    ))}
                  </select>
                  {syncCompanyFile && !(desktopCompanyAccountMap[syncCompanyFile] || '').trim() && !workspaceQuickbooksAccount && (
                    <p className="mt-1 text-xs text-amber-600">Set account in Settings → QuickBooks SDK Sync.</p>
                  )}
                </div>
              )}
              <button
                type="button"
                onClick={handleSelectAll}
                className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 hover:border-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 transition-colors cursor-pointer whitespace-nowrap"
              >
                {selectedIds.size === notSyncedIds.size ? (
                  <FaCheckSquare className="text-blue-600 flex-shrink-0" aria-hidden />
                ) : (
                  <FaSquare className="text-gray-500 flex-shrink-0" aria-hidden />
                )}
                <span>{selectedIds.size === notSyncedIds.size ? 'Deselect all' : 'Select all not synced'}</span>
              </button>
              <Button
                onClick={() => handleSyncSelected()}
                disabled={syncing || selectedIds.size === 0}
                variant="primary"
                className={`text-sm inline-flex items-center whitespace-nowrap ${selectedIds.size === 0 ? 'opacity-70 cursor-not-allowed' : ''}`}
              >
                <FaSync className={`flex-shrink-0 ${syncing ? 'animate-spin mr-2' : 'mr-2'}`} aria-hidden />
                <span>
                  {syncing
                    ? 'Syncing...'
                    : selectedIds.size > 0
                    ? `Sync ${selectedIds.size} to QuickBooks`
                    : 'Sync selected to QuickBooks'}
                </span>
              </Button>
            </div>
          )}
        </div>

        {message && (
          <div
            className={`mb-4 px-4 py-3 rounded-lg text-sm ${
              messageType === 'success'
                ? 'bg-green-50 text-green-800'
                : messageType === 'warning'
                ? 'bg-amber-50 text-amber-800'
                : 'bg-red-50 text-red-800'
            }`}
          >
            {message}
          </div>
        )}

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
                        // Update local extraction data with the user-entered payee
                        const txn = missingPayeeTxns[i]
                        if (txn.file_id != null && txn.transaction_index != null) {
                          setFilesWithStatus(prev => prev.map(item => {
                            if (item.file.id !== txn.file_id) return item
                            const txns = item.extraction?.processed_data?.transactions
                            if (!txns?.[txn.transaction_index]) return item
                            const updatedTxns = [...txns]
                            updatedTxns[txn.transaction_index] = { ...updatedTxns[txn.transaction_index], payee: payeeName }
                            return {
                              ...item,
                              extraction: {
                                ...item.extraction,
                                processed_data: { ...item.extraction.processed_data, transactions: updatedTxns }
                              }
                            }
                          }))
                        }
                      }

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

                      const remainingMissing = missingPayeeTxns.filter((_, idx) => {
                        const inp = missingPayeeInputs[idx] || {}
                        return !((inp.payeeName ?? '').trim() && (inp.expenseAccount ?? '').trim())
                      })
                      // Re-check using local transactions (which now have updated payee names)
                      const recheckTxns = []
                      for (const { file, extraction: ext } of filesWithStatus) {
                        if (!selectedIds.has(file.id)) continue
                        const txns = ext?.processed_data?.transactions || []
                        txns.forEach((t, idx) => recheckTxns.push({ ...t, _file_id: file.id, _transaction_index: idx }))
                      }
                      const recheckRes = await qbQueueAPI.checkUnmappedPayees(workspaceId, { transactionList: recheckTxns })
                      const stillUnmapped = recheckRes.unmapped_payees || []
                      if (stillUnmapped.length === 0 && remainingMissing.length === 0) {
                        setShowUnmappedModal(false)
                        setUnmappedPayees([])
                        setUnmappedExpenseAccounts({})
                        setMissingPayeeTxns([])
                        setMissingPayeeInputs({})
                        setMessage(saved ? 'Mappings saved. All payees are mapped. You can now sync.' : '')
                        setMessageType('success')
                      } else {
                        setUnmappedPayees(stillUnmapped)
                        setUnmappedExpenseAccounts({})
                        setMissingPayeeTxns(remainingMissing)
                        setMissingPayeeInputs({})
                        setMessage(saved ? `Saved ${saved} mapping(s). Fill in the remaining payees below.` : '')
                        setMessageType('warning')
                      }
                    } catch (err) {
                      console.error('Failed to save payee mappings:', err)
                      setMessage(`Error: ${err?.message || 'Failed to save mappings'}`)
                      setMessageType('error')
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
                      const skip = new Set(missingPayeeTxns.map(t => `${t.file_id}-${t.transaction_index}`))
                      setShowUnmappedModal(false)
                      setUnmappedPayees([])
                      setUnmappedExpenseAccounts({})
                      setMissingPayeeTxns([])
                      setMissingPayeeInputs({})
                      handleSyncSelected(skip)
                    }}
                    disabled={savingMappings}
                  >
                    Skip these & sync rest
                  </Button>
                )}
                <Button
                  variant="secondary"
                  onClick={() => { setShowUnmappedModal(false); setUnmappedPayees([]); setUnmappedExpenseAccounts({}); setMissingPayeeTxns([]); setMissingPayeeInputs({}) }}
                  disabled={savingMappings}
                >
                  Close
                </Button>
              </div>
              {message && showUnmappedModal && (
                <p className={`mt-3 text-sm ${message.startsWith('Error') ? 'text-red-600' : 'text-green-700'}`}>
                  {message}
                </p>
              )}
            </div>
          </div>
        )}

        {filesWithStatus.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            No single-check files found. Upload and process some checks, then return here to sync them.
          </div>
        ) : (
          <div className="space-y-2 max-h-[60vh] overflow-y-auto">
            {filesWithStatus.map(({ file, synced }) => (
              <div
                key={file.id}
                className={`flex items-center justify-between p-4 rounded-lg ${
                  selectedIds.has(file.id) ? 'bg-blue-50 border-2 border-blue-300' : 'bg-gray-50 hover:bg-gray-100'
                }`}
              >
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  {!synced ? (
                    <button
                      type="button"
                      onClick={() => handleSelect(file.id)}
                      className="flex-shrink-0 p-1 -m-1 rounded hover:bg-gray-200/80 cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1"
                      aria-label={selectedIds.has(file.id) ? 'Deselect' : 'Select'}
                    >
                      {selectedIds.has(file.id) ? (
                        <FaCheckSquare className="text-blue-600 text-lg" />
                      ) : (
                        <FaSquare className="text-gray-500 hover:text-gray-700 text-lg" />
                      )}
                    </button>
                  ) : (
                    <span className="w-8 flex-shrink-0" aria-hidden />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">{file.original_filename}</p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {new Date(file.created_at).toLocaleDateString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        year: 'numeric',
                      })}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3 ml-4">
                  <span
                    className={`px-3 py-1 text-xs font-semibold rounded-full ${
                      synced ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'
                    }`}
                  >
                    {synced ? 'Synced' : 'Not synced'}
                  </span>
                  <button
                    type="button"
                    onClick={() => navigate(`/extracted/${file.id}`)}
                    className="text-blue-600 hover:text-blue-900"
                    title="View extraction"
                  >
                    <FaEye className="text-base" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}

export default SyncChecks
