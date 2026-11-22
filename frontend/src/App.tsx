import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout.tsx'
import LoginPage from './pages/LoginPage.tsx'
import ProfilePage from './pages/ProfilePage.tsx'
import DiagnosisPage from './pages/DiagnosisPage.tsx'
import ResultPage from './pages/ResultPage.tsx'
import PlanPage from './pages/PlanPage.tsx'
import BlockPage from './pages/BlockPage.tsx'
import AcademicPage from './pages/AcademicPage.tsx'
import { getAuthToken } from './api.ts'

// 주소만 치고 들어오면 로그인돼 있으면 플랜으로, 아니면 로그인으로
function Home() {
  return <Navigate to={getAuthToken() ? '/plan' : '/login'} replace />
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
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
