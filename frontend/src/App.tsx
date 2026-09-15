import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { LoginPage } from './pages/LoginPage'
import { CallbackPage } from './pages/CallbackPage'
import { WorkbenchPage } from './pages/WorkbenchPage'
import './App.css'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/login/callback" element={<CallbackPage />} />
        <Route path="/auth/callback" element={<CallbackPage />} />
        <Route path="/workbench" element={<WorkbenchPage />} />
        <Route path="/" element={<Navigate to="/workbench" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
