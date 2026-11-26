import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth.jsx'
import Layout from './components/Layout.jsx'
import Login from './pages/Login.jsx'
import Callback from './pages/Callback.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Profile from './pages/Profile.jsx'
import Topics from './pages/Topics.jsx'
import RequestForm from './pages/RequestForm.jsx'
import Pool from './pages/Pool.jsx'
import RequestDetail from './pages/RequestDetail.jsx'
import Chat from './pages/Chat.jsx'
import Projects from './pages/Projects.jsx'
import ProjectDetail from './pages/ProjectDetail.jsx'
import Research from './pages/Research.jsx'
import Lab from './pages/Lab.jsx'
import Practicum from './pages/Practicum.jsx'
import Internship from './pages/Internship.jsx'
import InternshipDashboard from './pages/InternshipDashboard.jsx'
import AiAssistant from './pages/AiAssistant.jsx'
import Semantic from './pages/Semantic.jsx'
import Admin from './pages/Admin.jsx'
import SsoSettings from './pages/SsoSettings.jsx'

function Protected({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="login-wrap"><div className="sub">در حال بارگذاری…</div></div>
  if (!user) return <Navigate to="/login" replace />
  return <Layout>{children}</Layout>
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/sso/callback" element={<Callback />} />
        <Route path="/" element={<Protected><Dashboard /></Protected>} />
        <Route path="/profile" element={<Protected><Profile /></Protected>} />
        <Route path="/topics" element={<Protected><Topics /></Protected>} />
        <Route path="/requests/new" element={<Protected><RequestForm /></Protected>} />
        <Route path="/requests/:id" element={<Protected><RequestDetail /></Protected>} />
        <Route path="/pool" element={<Protected><Pool /></Protected>} />
        <Route path="/chat/:requestId?" element={<Protected><Chat /></Protected>} />
        <Route path="/projects" element={<Protected><Projects /></Protected>} />
        <Route path="/projects/:id" element={<Protected><ProjectDetail /></Protected>} />
        <Route path="/research" element={<Protected><Research /></Protected>} />
        <Route path="/research/:id" element={<Protected><Research /></Protected>} />
        <Route path="/lab" element={<Protected><Lab /></Protected>} />
        <Route path="/practicum" element={<Protected><Practicum /></Protected>} />
        <Route path="/internship" element={<Protected><Internship /></Protected>} />
        <Route path="/internship-dashboard" element={<Protected><InternshipDashboard /></Protected>} />
        <Route path="/ai" element={<Protected><AiAssistant /></Protected>} />
        <Route path="/semantic" element={<Protected><Semantic /></Protected>} />
        <Route path="/admin" element={<Protected><Admin /></Protected>} />
        <Route path="/admin/sso" element={<Protected><SsoSettings /></Protected>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}
