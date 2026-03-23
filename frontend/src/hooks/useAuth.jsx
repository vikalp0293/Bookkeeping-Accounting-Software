import { createContext, useContext, useState, useEffect } from 'react'
import { authAPI } from '../utils/api'
import storage from '../utils/storage'
import { isElectron } from '../utils/electron-api'

const AuthContext = createContext(null)

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const refreshAccessToken = async () => {
    try {
      const refreshToken = isElectron()
        ? await storage.getItemAsync('refresh_token')
        : storage.getItem('refresh_token')
      
      if (!refreshToken) {
        return false
      }
      
      const response = await authAPI.refreshToken(refreshToken)
      
      // Save new access token
      if (isElectron()) {
        await storage.setItemAsync('access_token', response.access_token)
      } else {
        storage.setItem('access_token', response.access_token)
      }
      
      return true
    } catch (error) {
      console.error('Token refresh failed:', error)
      // Refresh token expired, clear everything
      if (isElectron()) {
        await storage.removeItemAsync('access_token')
        await storage.removeItemAsync('refresh_token')
      } else {
        storage.removeItem('access_token')
        storage.removeItem('refresh_token')
      }
      return false
    }
  }

  const loadUser = async () => {
    try {
      const userData = await authAPI.getCurrentUser()
      setUser(userData)
    } catch (error) {
      // Token might be invalid, try to refresh
      if (error.message && error.message.includes('401')) {
        const refreshed = await refreshAccessToken()
        if (refreshed) {
          // Retry getting user after refresh
          try {
            const userData = await authAPI.getCurrentUser()
            setUser(userData)
            return
          } catch (retryError) {
            // Still failed, but for Electron, don't log out immediately
            // The refresh token might still be valid, just wait for next refresh cycle
            if (isElectron()) {
              console.warn('Failed to load user after refresh, but keeping session for Electron')
              // Don't clear tokens - let the automatic refresh handle it
              setUser(null)
              setLoading(false)
              return
            }
            // For web, clear tokens
          }
        } else {
          // Refresh failed - for Electron, only clear if refresh token is truly expired
          // The refreshAccessToken function already handles clearing expired refresh tokens
          if (!isElectron()) {
            // For web, clear tokens on refresh failure
            storage.removeItem('access_token')
            storage.removeItem('refresh_token')
          }
        }
      }
      
      // Only clear tokens for web or if it's not a 401 error
      if (!isElectron() || !error.message?.includes('401')) {
        if (isElectron()) {
          await storage.removeItemAsync('access_token')
          await storage.removeItemAsync('refresh_token')
        } else {
          storage.removeItem('access_token')
          storage.removeItem('refresh_token')
        }
        setUser(null)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    // Check if user is already logged in
    const checkAuth = async () => {
      // Use async version for Electron, sync for web
      const token = isElectron() 
        ? await storage.getItemAsync('access_token')
        : storage.getItem('access_token')
      
      if (token) {
        await loadUser()
      } else {
        setLoading(false)
      }
    }
    checkAuth()
    
    // Set up automatic token refresh for Electron (keep signed in)
    if (isElectron()) {
      // Refresh token more frequently to prevent expiration
      // Refresh every 1 hour to ensure token is always fresh (access token expires in 24h)
      const refreshInterval = setInterval(async () => {
        const refreshToken = await storage.getItemAsync('refresh_token')
        if (refreshToken) {
          // Silently refresh token in background
          try {
            await refreshAccessToken()
            console.log('Token refreshed automatically')
          } catch (error) {
            console.error('Automatic token refresh failed:', error)
            // If refresh fails, don't log out - user might still be valid
            // Only log out if refresh token is truly expired (handled in refreshAccessToken)
          }
        }
      }, 60 * 60 * 1000) // 1 hour (more frequent to prevent expiration)
      
      return () => clearInterval(refreshInterval)
    }
  }, [])

  const login = async (email, password) => {
    try {
      const response = await authAPI.login(email, password)
      if (isElectron()) {
        await storage.setItemAsync('access_token', response.access_token)
        await storage.setItemAsync('refresh_token', response.refresh_token)
      } else {
        storage.setItem('access_token', response.access_token)
        storage.setItem('refresh_token', response.refresh_token)
      }
      await loadUser()
      return { success: true }
    } catch (error) {
      return { success: false, error: error.message }
    }
  }

  const logout = () => {
    if (isElectron()) {
      storage.removeItemAsync('access_token').catch(() => {})
      storage.removeItemAsync('refresh_token').catch(() => {})
    } else {
      storage.removeItem('access_token')
      storage.removeItem('refresh_token')
    }
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, loadUser, refreshAccessToken }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}

