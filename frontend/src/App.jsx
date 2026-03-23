import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './hooks/useAuth'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Upload from './pages/Upload'
import Extracted from './pages/Extracted'
import Settings from './pages/Settings'
import ReviewQueue from './pages/ReviewQueue'
import OCRLogs from './pages/OCRLogs'
import ActivityLogs from './pages/ActivityLogs'
import LogViewer from './pages/LogViewer'
import PayeeManagement from './pages/PayeeManagement'
import SyncChecks from './pages/SyncChecks'
import UserManagement from './pages/UserManagement'
import PrivateRoute from './components/PrivateRoute'
import Layout from './components/Layout'

function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <PrivateRoute>
                <Layout />
              </PrivateRoute>
            }
          >
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="upload" element={<Upload />} />
            <Route path="extracted/:id" element={<Extracted />} />
            <Route path="review-queue" element={<ReviewQueue />} />
            <Route path="settings" element={<Settings />} />
            <Route path="logs/ocr" element={<OCRLogs />} />
            <Route path="logs/activity" element={<ActivityLogs />} />
            <Route path="logs" element={<LogViewer />} />
            <Route path="payees" element={<PayeeManagement />} />
            <Route path="sync-checks" element={<SyncChecks />} />
            <Route path="users" element={<UserManagement />} />
          </Route>
        </Routes>
      </Router>
    </AuthProvider>
  )
}

export default App

