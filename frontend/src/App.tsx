import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout.tsx'
import LoginPage from './pages/LoginPage.tsx'
import ProfilePage from './pages/ProfilePage.tsx'
import DiagnosisPage from './pages/DiagnosisPage.tsx'
import ResultPage from './pages/ResultPage.tsx'
import PlanPage from './pages/PlanPage.tsx'
import BlockPage from './pages/BlockPage.tsx'
import AcademicPage from './pages/AcademicPage.tsx'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/login" replace />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="diagnosis" element={<DiagnosisPage />} />
        <Route path="result" element={<ResultPage />} />
        <Route path="plan" element={<PlanPage />} />
        <Route path="blocks/:blockId" element={<BlockPage />} />
        <Route path="academic" element={<AcademicPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Route>
    </Routes>
  )
}
