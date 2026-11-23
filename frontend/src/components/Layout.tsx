import { useSyncExternalStore } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { getAuthToken, setAuthToken, subscribeAuthToken } from '../api.ts'

const NAV_ITEMS = [
  { to: '/profile', label: '프로필' },
  { to: '/diagnosis', label: '진단' },
  { to: '/result', label: '결과' },
  { to: '/plan', label: '플랜' },
  { to: '/academic', label: '학사 안내' },
]

/** 로그인 상태. 로그인·로그아웃하면 바로 다시 그린다 */
function useLoggedIn(): boolean {
  return useSyncExternalStore(subscribeAuthToken, getAuthToken) !== null
}

export default function Layout() {
  const loggedIn = useLoggedIn()
  const navigate = useNavigate()

  function handleLogout() {
    setAuthToken(null)
    navigate('/login', { replace: true })
  }

  return (
    <>
      <a href="#main" className="skip-link">
        본문으로 건너뛰기
      </a>
      <header className="layout-header">
        <nav className="layout-nav">
          <Link to={loggedIn ? '/plan' : '/login'} className="brand">
            <img src="/favicon.svg" alt="" className="brand-mark" width={28} height={28} />
            브릿지
          </Link>
          {!loggedIn && (
            <NavLink to="/login" className="layout-login">
              로그인
            </NavLink>
          )}
          {/* 로그인 전에는 눌러도 로그인 화면으로 돌아가므로 메뉴를 숨긴다 */}
          {loggedIn &&
            NAV_ITEMS.map((item) => (
              <NavLink key={item.to} to={item.to}>
                {item.label}
              </NavLink>
            ))}
          {loggedIn && (
            <button type="button" className="layout-logout" onClick={handleLogout}>
              로그아웃
            </button>
          )}
        </nav>
      </header>
      <main id="main" className="layout-main" tabIndex={-1}>
        <Outlet />
      </main>
    </>
  )
}
