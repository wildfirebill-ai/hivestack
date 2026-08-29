import { HashRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Layout from './Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Chat from './pages/Chat'
import Agents from './pages/Agents'
import Workflows from './pages/Workflows'
import Boards from './pages/Boards'
import Memory from './pages/Memory'
import Skills from './pages/Skills'
import Studio from './pages/Studio'
import Comms from './pages/Comms'
import AIOps from './pages/AIOps'
import Governance from './pages/Governance'
import Economy from './pages/Economy'
import Settings from './pages/Settings'
import { getToken } from './api'

function Guard({ children }: { children: React.ReactNode }) {
  const loc = useLocation()
  if (!getToken()) return <Navigate to="/login" replace state={{ from: loc.pathname }} />
  return <>{children}</>
}

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <Guard>
              <Layout />
            </Guard>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="chat" element={<Chat />} />
          <Route path="agents" element={<Agents />} />
          <Route path="workflows" element={<Workflows />} />
          <Route path="boards" element={<Boards />} />
          <Route path="memory" element={<Memory />} />
          <Route path="skills" element={<Skills />} />
          <Route path="studio" element={<Studio />} />
          <Route path="comms" element={<Comms />} />
          <Route path="aiops" element={<AIOps />} />
          <Route path="governance" element={<Governance />} />
          <Route path="economy" element={<Economy />} />
          <Route path="settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </HashRouter>
  )
}