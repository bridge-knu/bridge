import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, login, setAuthToken } from '../api.ts'

const PIN_PATTERN = /^\d{4}$/

// 입력값 검증. 문제가 없으면 null.
function validate(loginId: string, pin: string): string | null {
  if (!loginId) return '아이디를 입력해 주세요'
  if (!PIN_PATTERN.test(pin)) return 'PIN은 숫자 4자리로 입력해 주세요'
  return null
}

// 서버가 보낸 안내 문구(detail)를 우선 쓰고, 없으면 상태 코드별 기본 문구를 쓴다.
function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.detail) return err.detail
    if (err.status === 401) return '아이디 또는 PIN이 틀렸어요'
    if (err.status === 429) return '1분 후 다시 시도해 주세요'
    return '잠시 후 다시 시도해 주세요'
  }
  // fetch 자체가 실패한 경우 (서버 꺼짐, 네트워크 끊김)
  return '서버에 연결할 수 없어요. 네트워크를 확인해 주세요'
}

export default function LoginPage() {
  const navigate = useNavigate()
  const [loginId, setLoginId] = useState('')
  const [pin, setPin] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (loading) return

    const id = loginId.trim()
    const invalid = validate(id, pin)
    if (invalid) {
      setError(invalid)
      return
    }

    setError(null)
    setLoading(true)
    try {
      const res = await login(id, pin)
      // 토큰은 api.ts의 메모리에만 둔다 (브라우저 저장소에 저장하지 않음)
      setAuthToken(res.token)
      // 새 사용자는 프로필 입력부터, 기존 사용자는 플랜으로
      navigate(res.isNewUser ? '/profile' : '/plan', { replace: true })
    } catch (err) {
      setError(errorMessage(err))
      setPin('')
      setLoading(false)
    }
  }

  return (
    <section className="login">
      <h1>로그인</h1>
      <p className="login-hint">처음 쓰는 아이디면 자동으로 가입돼요.</p>

      <form className="login-form" onSubmit={handleSubmit} noValidate>
        <label>
          아이디
          <input
            type="text"
            name="loginId"
            autoComplete="username"
            autoFocus
            maxLength={30}
            value={loginId}
            onChange={(e) => setLoginId(e.target.value)}
            disabled={loading}
          />
        </label>

        <label>
          PIN (숫자 4자리)
          <input
            type="password"
            name="pin"
            inputMode="numeric"
            autoComplete="current-password"
            maxLength={4}
            value={pin}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 4))}
            disabled={loading}
          />
        </label>

        {error && (
          <p className="login-error" role="alert">
            {error}
          </p>
        )}

        <button type="submit" disabled={loading}>
          {loading ? '로그인 중…' : '로그인'}
        </button>
      </form>
    </section>
  )
}
