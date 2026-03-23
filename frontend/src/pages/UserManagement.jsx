import { useEffect, useMemo, useState } from 'react'
import Card from '../components/Card'
import Button from '../components/Button'
import Input from '../components/Input'
import { useAuth } from '../hooks/useAuth'
import { userManagementAPI } from '../utils/api'

const UserManagement = () => {
  const { user } = useAuth()
  const role = (user?.role || (user?.is_superuser ? 'superuser' : '')).toLowerCase()
  const isSuperuser = role === 'superuser'
  const isAdmin = role === 'admin'

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [users, setUsers] = useState([])

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [workspaceName, setWorkspaceName] = useState('')
  const [newRole, setNewRole] = useState('reviewer')

  const title = useMemo(() => {
    if (isSuperuser) return 'User Management (Superuser)'
    if (isAdmin) return 'User Management (Admin)'
    return 'User Management'
  }, [isSuperuser, isAdmin])

  const loadUsers = async () => {
    setLoading(true)
    setError('')
    try {
      if (isSuperuser) {
        const list = await userManagementAPI.listUsers({ role: 'admin' })
        setUsers(Array.isArray(list) ? list : [])
      } else if (isAdmin) {
        const list = await userManagementAPI.listUsers()
        setUsers(Array.isArray(list) ? list : [])
      } else {
        setUsers([])
      }
    } catch (e) {
      setError(e.message || 'Failed to load users')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadUsers()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role])

  const handleCreate = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    setMessage('')
    try {
      if (isSuperuser) {
        await userManagementAPI.createAdmin({
          email,
          password,
          full_name: fullName || null,
          workspace_name: workspaceName || null,
        })
        setMessage('Admin user created.')
      } else if (isAdmin) {
        await userManagementAPI.createWorkspaceUser({
          email,
          password,
          full_name: fullName || null,
          role: newRole,
        })
        setMessage(`${newRole} user created.`)
      } else {
        setError('You do not have permission to create users.')
        return
      }

      setEmail('')
      setPassword('')
      setFullName('')
      setWorkspaceName('')
      setNewRole('reviewer')
      await loadUsers()
    } catch (e2) {
      setError(e2.message || 'Failed to create user')
    } finally {
      setLoading(false)
    }
  }

  if (!isSuperuser && !isAdmin) {
    return (
      <Card title="User Management" subtitle="Not available for your role">
        <p className="text-sm text-gray-600">Your role does not have access to user management.</p>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
          <p className="text-sm text-gray-600">
            {isSuperuser
              ? 'Create Admin users (each gets a new workspace).'
              : 'Create Reviewer/Accountant users for your workspace.'}
          </p>
        </div>
        <Button type="button" variant="secondary" onClick={loadUsers} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </Button>
      </div>

      {(error || message) && (
        <div className="space-y-2">
          {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">{error}</div>}
          {message && <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg">{message}</div>}
        </div>
      )}

      <Card
        title={isSuperuser ? 'Create Admin' : 'Create Workspace User'}
        subtitle={isSuperuser ? 'Superuser-only' : 'Admin-only'}
      >
        <form className="space-y-4" onSubmit={handleCreate}>
          <Input
            label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="user@company.com"
            required
          />
          <Input
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Minimum 8 characters"
            required
          />
          <Input
            label="Full Name"
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Optional"
          />

          {isSuperuser ? (
            <Input
              label="Workspace Name"
              type="text"
              value={workspaceName}
              onChange={(e) => setWorkspaceName(e.target.value)}
              placeholder="Optional (defaults to user's workspace name)"
            />
          ) : (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              >
                <option value="reviewer">Reviewer</option>
                <option value="accountant">Accountant</option>
              </select>
              <p className="mt-1 text-xs text-gray-500">User will be added to your workspace.</p>
            </div>
          )}

          <Button type="submit" variant="primary" disabled={loading}>
            {loading ? 'Creating...' : 'Create user'}
          </Button>
        </form>
      </Card>

      <Card title="Users" subtitle={isSuperuser ? 'Admins' : 'Users in your workspace'}>
        <div className="overflow-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-gray-600">
                <th className="py-2 pr-4">ID</th>
                <th className="py-2 pr-4">Email</th>
                <th className="py-2 pr-4">Name</th>
                <th className="py-2 pr-4">Role</th>
                <th className="py-2 pr-4">Workspace</th>
                <th className="py-2 pr-4">Active</th>
              </tr>
            </thead>
            <tbody className="text-gray-800">
              {users.length === 0 && (
                <tr>
                  <td className="py-3 text-gray-500" colSpan={6}>
                    No users found.
                  </td>
                </tr>
              )}
              {users.map((u) => (
                <tr key={u.id} className="border-t border-gray-100">
                  <td className="py-2 pr-4">{u.id}</td>
                  <td className="py-2 pr-4">{u.email}</td>
                  <td className="py-2 pr-4">{u.full_name || ''}</td>
                  <td className="py-2 pr-4">{u.role}</td>
                  <td className="py-2 pr-4">{u.workspace_id ?? ''}</td>
                  <td className="py-2 pr-4">{u.is_active ? 'Yes' : 'No'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

export default UserManagement

