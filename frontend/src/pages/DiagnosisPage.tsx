import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, setAuthToken } from '../api.ts'
import { classifyDiagnosisError } from '../diagnosis/errors.ts'
import { diagnosisSource, type DiagnosisStep } from '../diagnosis/source.ts'

type Phase = 'intro' | 'question' | 'done'

const NEED_CHOICE = '보기를 하나 골라 주세요'

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.detail ?? '잠시 후 다시 시도해 주세요'
  if (err instanceof TypeError) return '서버에 연결할 수 없어요. 네트워크를 확인해 주세요'
  return '문제를 불러오지 못했어요. 다시 시도해 주세요'
}

export default function DiagnosisPage() {
  const navigate = useNavigate()
  const [phase, setPhase] = useState<Phase>('intro')
  const [step, setStep] = useState<DiagnosisStep | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // 400 "지금 풀고 있는 문제가 아니에요"는 같은 답을 다시 내도 계속 실패하므로 처음부터 다시 시작하게 한다.
  const [needsRestart, setNeedsRestart] = useState(false)
  // 같은 틱에 두 번 눌러도 요청이 한 번만 나가게 한다 (loading state는 다음 렌더에야 반영됨).
  const inFlight = useRef(false)

  // start·answer 공통: 다음 단계를 받아 화면 상태를 바꾼다.
  async function run(load: () => Promise<DiagnosisStep>) {
    if (inFlight.current) return
    inFlight.current = true
    setLoading(true)
    setError(null)
    setNeedsRestart(false)
    try {
      const next = await load()
      setStep(next)
      setSelected(null)
      setPhase(next.question ? 'question' : 'done')
    } catch (err) {
      const kind = classifyDiagnosisError(err)
      // 토큰이 없거나 만료됨 (새로고침하면 메모리 토큰이 사라짐) → 다시 로그인
      if (kind === 'unauthorized') {
        setAuthToken(null)
        navigate('/login', { replace: true })
        return
      }
      // 이미 끝난 진단은 다시 시작하면 결과가 지워지므로 완료 화면으로 보낸다.
      if (kind === 'finished') {
        setPhase('done')
        return
      }
      if (kind === 'mismatch') setNeedsRestart(true)
      setError(errorMessage(err))
    } finally {
      inFlight.current = false
      setLoading(false)
    }
  }

  function handleStart() {
    if (!loading) void run(() => diagnosisSource.start())
  }

  function handleSubmit() {
    const question = step?.question
    if (loading || !question) return
    if (selected === null) {
      setError(NEED_CHOICE)
      return
    }
    void run(() => diagnosisSource.answer(question.id, selected))
  }

  if (phase === 'intro') {
    return (
      <section className="form-page">
        <h1>진단</h1>
        <p className="form-hint">
          목표 과목에 필요한 개념을 문제로 확인해요. 틀리면 더 기초 개념으로 내려가며, 최대 10문제예요.
        </p>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <div className="form">
          <button type="button" onClick={handleStart} disabled={loading}>
            {loading ? '불러오는 중…' : '진단 시작'}
          </button>
        </div>
      </section>
    )
  }

  if (phase === 'done' || !step?.question) {
    return (
      <section className="form-page">
        <h1>진단 완료</h1>
        <p className="form-hint">수고했어요. 결과 화면에서 아는 개념과 보충할 개념을 확인해 보세요.</p>
        <div className="form">
          <button type="button" onClick={() => navigate('/result')}>
            결과 보기
          </button>
        </div>
      </section>
    )
  }

  const { question, number, total } = step

  return (
    <section className="form-page">
      <div className="diagnosis-progress">
        <span>
          문제 {number} / {total}
        </span>
        <progress value={number} max={total} aria-label="진단 진행률" />
      </div>

      <h1 className="diagnosis-prompt">{question.prompt}</h1>

      {question.code && (
        <pre className="diagnosis-code">
          <code>{question.code}</code>
        </pre>
      )}

      <div className="form">
        <fieldset className="diagnosis-choices" disabled={loading}>
          <legend>보기</legend>
          {question.choices.map((choice, i) => (
            <label key={`${question.id}-${i}`} className={selected === i ? 'selected' : undefined}>
              <input
                type="radio"
                name={question.id}
                checked={selected === i}
                onChange={() => {
                  setSelected(i)
                  if (error === NEED_CHOICE) setError(null)
                }}
              />
              {choice}
            </label>
          ))}
        </fieldset>

        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}

        {needsRestart && (
          <button type="button" onClick={handleStart} disabled={loading}>
            진단 다시 시작
          </button>
        )}

        <button type="button" onClick={handleSubmit} disabled={loading}>
          {loading ? '제출 중…' : number < total ? '다음 문제' : '제출하고 끝내기'}
        </button>
      </div>
    </section>
  )
}
