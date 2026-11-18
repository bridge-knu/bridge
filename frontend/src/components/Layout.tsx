import { Link, NavLink, Outlet } from 'react-router-dom'

const NAV_ITEMS = [
  { to: '/login', label: '로그인' },
  { to: '/profile', label: '프로필' },
  { to: '/diagnosis', label: '진단' },
  { to: '/result', label: '결과' },
  { to: '/plan', label: '플랜' },
  { to: '/academic', label: '학사 안내' },
]

export default function Layout() {
  return (
    <>
      <header className="layout-header">
        <nav className="layout-nav">
          <Link to="/" className="brand">브릿지</Link>
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="layout-main">
        <Outlet />
      </main>
    </>
  )
}
