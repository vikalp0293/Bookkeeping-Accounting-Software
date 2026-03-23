import { useState, useEffect } from 'react'
import { useAuth } from '../hooks/useAuth'
import Card from '../components/Card'
import Input from '../components/Input'
import Button from '../components/Button'
import DesktopSettings from '../components/DesktopSettings'
import { isElectron } from '../utils/electron-api'
import { workspacesAPI } from '../utils/api'

const Settings = () => {
  const { user } = useAuth()
  const [formData, setFormData] = useState({
    full_name: '',
    email: '',
  })
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (user) {
      setFormData({
        full_name: user.full_name || '',
        email: user.email || '',
      })
    }
  }, [user])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setMessage('')

    // Placeholder for update functionality
    setTimeout(() => {
      setMessage('Settings updated successfully!')
      setLoading(false)
    }, 1000)
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Settings</h1>

      {/* Desktop-specific settings */}
      {isElectron() && <DesktopSettings />}

      <Card title="Profile Information" subtitle="Update your account information">
        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Full Name"
            type="text"
            value={formData.full_name}
            onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
            placeholder="John Doe"
          />
          <Input
            label="Email"
            type="email"
            value={formData.email}
            onChange={(e) => setFormData({ ...formData, email: e.target.value })}
            placeholder="you@example.com"
            disabled
          />
          {message && (
            <div
              className={`p-3 rounded-lg ${
                message.includes('success')
                  ? 'bg-green-50 text-green-700'
                  : 'bg-red-50 text-red-700'
              }`}
            >
              {message}
            </div>
          )}
          <Button type="submit" variant="primary" disabled={loading}>
            {loading ? 'Saving...' : 'Save Changes'}
          </Button>
        </form>
      </Card>

    </div>
  )
}

export default Settings

