import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// 개발 서버용 API 프록시 설정.
// 백엔드 라우터에는 /api 접두어가 없다. 프론트는 /api/... 로 부르고,
// 이 프록시가 접두어를 떼서 넘긴다 (/api/auth/login → /auth/login).
// 배포 환경에서는 Caddy가 같은 규칙으로 /api를 떼고 백엔드로 넘긴다.
// 아래 두 값은 frontend/.env 에서 바꿀 수 있다 (.env.example 참고).
// - VITE_API_BASE: API 경로 접두어. src/api.ts 도 같은 값을 쓴다.
// - BACKEND_URL: 요청을 넘길 FastAPI 주소.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  const apiBase = env.VITE_API_BASE || '/api'
  const backendUrl = env.BACKEND_URL || 'http://localhost:8000'

  return {
    plugins: [react()],
    server: {
      proxy: {
        [apiBase]: {
          target: backendUrl,
          changeOrigin: true,
          rewrite: (path: string) => path.slice(apiBase.length) || '/',
        },
      },
    },
  }
})
