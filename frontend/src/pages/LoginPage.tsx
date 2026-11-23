import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { ApiError, getAuthToken, login, setAuthToken, startTrial } from '../api.ts'

const PIN_PATTERN = /^\d{4}$/

// 휴대폰에서는 들어오자마자 키보드가 올라와 소개를 가리므로, 마우스를 쓰는 기기에서만 아이디 칸에 바로 포커스를 준다
const FOCUS_ON_LOAD = typeof window !== 'undefined' && window.matchMedia?.('(pointer: fine)').matches === true

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
  const [trialLoading, setTrialLoading] = useState(false)
  const busy = loading || trialLoading

  // 체험하기: 데모 데이터가 채워진 나만의 계정을 새로 받아 바로 플랜으로
  async function handleTrial() {
    if (busy) return
    setError(null)
    setTrialLoading(true)
    try {
      const res = await startTrial()
      setAuthToken(res.token)
      navigate('/plan', { replace: true })
    } catch (err) {
      setError(`${errorMessage(err)} (데모 계정 demo / 0000으로도 들어올 수 있어요)`)
      setTrialLoading(false)
    }
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (busy) return

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
      // 토큰은 api.ts가 sessionStorage에 둔다 (새로고침해도 유지, 탭을 닫으면 지워짐)
      setAuthToken(res.token)
      // 새 사용자는 프로필 입력부터, 기존 사용자는 플랜으로
      navigate(res.isNewUser ? '/profile' : '/plan', { replace: true })
    } catch (err) {
      setError(errorMessage(err))
      setPin('')
      setLoading(false)
    }
  }

  // 이미 로그인한 상태로 로그인 화면에 오면 폼 대신 플랜으로 보낸다
  if (getAuthToken()) return <Navigate to="/plan" replace />

  return (
    <section className="login">
      <div className="login-intro">
        <p className="login-service">브릿지</p>
        <p className="login-tagline">복학 전에 잊은 선수 개념을 찾아, 복학일까지 공부 계획을 짜 드려요.</p>
        <ol className="login-steps">
          <li>몇 문제로 잊은 개념 진단</li>
          <li>아는 개념과 보충할 개념을 지도로 확인</li>
          <li>복학일까지 날짜별 30분 블록으로 학습</li>
        </ol>
      </div>

      <div className="login-panel">
        <h1>로그인</h1>
        <p className="login-hint">처음 쓰는 아이디면 자동으로 가입돼요.</p>
        <div className="login-demo">
          <p className="login-demo-title">직접 해 보려면 체험하기</p>
          <p>
            진단까지 끝난 나만의 계정이 바로 만들어져요. 진단을 다시 하거나 프로필을 바꿔도 다른 사람에게 영향이
            없어요.
          </p>
          <button type="button" className="block-button" onClick={handleTrial} disabled={busy}>
            {trialLoading ? '체험 계정 만드는 중…' : '체험하기'}
          </button>
          <p className="login-demo-fallback">
            둘러보기만 하려면 공용 데모 계정 <strong>demo</strong> / PIN <strong>0000</strong>도 돼요. 여러 명이
            같이 쓰는 계정이라 진단·프로필은 바꿀 수 없어요.
          </p>
        </div>

        <form className="login-form" onSubmit={handleSubmit} noValidate>
          <label>
            아이디
            <input
              type="text"
              name="loginId"
              autoComplete="username"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              autoFocus={FOCUS_ON_LOAD}
              maxLength={30}
              value={loginId}
              onChange={(e) => setLoginId(e.target.value)}
              disabled={busy}
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
              disabled={busy}
            />
          </label>

          {error && (
            <p className="login-error" role="alert">
              {error}
            </p>
          )}

          <button type="submit" disabled={busy}>
            {loading ? '로그인 중…' : '로그인'}
          </button>
        </form>
      </div>
    </section>
  )
}
