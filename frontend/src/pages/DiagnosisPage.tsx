import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, getDiagnosisResult, setAuthToken } from '../api.ts'
import { classifyDiagnosisError } from '../diagnosis/errors.ts'
import { finishReason, progressLabel } from '../diagnosis/finish.ts'
import { diagnosisReason, reasonTone, type ReasonTone } from '../diagnosis/reason.ts'
import { diagnosisSource, type DiagnosisStep } from '../diagnosis/source.ts'

type Phase = 'intro' | 'question' | 'done'

const NEED_CHOICE = '보기를 하나 골라 주세요'
const RESTART_CONFIRM = '다시 진단하면 지금 진단 결과가 지워지고 처음부터 다시 풀어요. 계속할까요?'
// 공용 데모 계정(demo)은 서버가 다시 시작을 막는다 (400 DIAGNOSIS_FINISHED, #54)
const RESTART_BLOCKED =
  '공용 데모 계정은 여러 사람이 함께 써서 다시 진단할 수 없어요. 진단을 직접 해 보려면 로그아웃한 뒤 로그인 화면의 ‘체험하기’로 나만의 계정을 만들어 주세요.'

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
  // 이미 끝낸 진단이 있는지 (null: 확인 중). 있으면 "진단 시작" 대신 결과 보기를 먼저 보여 준다.
  // 다시 시작하면 서버가 결과를 지우므로, 같이 쓰는 데모 계정에서 실수로 지우지 않게 한다.
  const [finished, setFinished] = useState<boolean | null>(null)
  // 지금 문제를 내는 이유 (직전 문제의 정답 여부와 선수 관계로 만든 한 줄)
  // 색은 직전 답에 맞춘다 (결과 그래프와 같은 약속: 파랑 = 아는 개념, 주황 = 보충할 개념)
  const [reason, setReason] = useState<{ text: string; tone: ReasonTone } | null>(null)
  // "다시 진단하기"로 시작했는지. 이때 서버가 막으면 완료 화면 대신 막힌 이유를 보여 준다
  const restarting = useRef(false)
  // 이번 진단에서 맞힌 문제 수 (완료 화면에서 일찍 끝난 이유를 고르는 데 쓴다)
  const [correctCount, setCorrectCount] = useState(0)
  const [restartBlocked, setRestartBlocked] = useState(false)

  useEffect(() => {
    let cancelled = false
    getDiagnosisResult()
      .then((res) => {
        if (!cancelled) setFinished(res.concepts.length > 0)
      })
      .catch(() => {
        // 미완료(400)·오류 모두 평소처럼 시작 화면. 로그인 만료(401)는 시작을 누를 때 처리한다
        if (!cancelled) setFinished(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // start·answer 공통: 다음 단계를 받아 화면 상태를 바꾼다.
  async function run(load: () => Promise<DiagnosisStep>, isStart: boolean) {
    if (inFlight.current) return
    inFlight.current = true
    setLoading(true)
    setError(null)
    setNeedsRestart(false)
    try {
      // 시작이면 직전 문제가 없다. 답을 낸 경우엔 방금 푼 문제가 step에 남아 있다
      const prev = isStart ? null : (step?.question ?? null)
      const next = await load()
      const correct = isStart ? null : next.correct
      if (isStart) setCorrectCount(0)
      else if (correct) setCorrectCount((c) => c + 1)
      const text = diagnosisReason({ prev, correct, next: next.question })
      setReason(text ? { text, tone: reasonTone(correct) } : null)
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
      if (kind === 'finished') {
        // 다시 진단하기를 서버가 막음 (공용 데모 계정) → 진단을 하지 않았으니 완료 화면 대신 이유를 알려 준다
        if (restarting.current) {
          setRestartBlocked(true)
          return
        }
        // 이미 끝난 진단은 다시 시작하면 결과가 지워지므로 완료 화면으로 보낸다.
        setPhase('done')
        return
      }
      if (kind === 'mismatch') setNeedsRestart(true)
      setError(errorMessage(err))
    } finally {
      inFlight.current = false
      restarting.current = false
      setLoading(false)
    }
  }

  function handleStart() {
    if (!loading) void run(() => diagnosisSource.start(), true)
  }

  function handleRestart() {
    if (loading || !window.confirm(RESTART_CONFIRM)) return
    restarting.current = true
    handleStart()
  }

  function handleSubmit() {
    const question = step?.question
    if (loading || !question) return
    if (selected === null) {
      setError(NEED_CHOICE)
      return
    }
    void run(() => diagnosisSource.answer(question.id, selected), false)
  }

  if (phase === 'intro' && finished) {
    return (
      <section className="form-page">
        <h1>진단</h1>
        <p className="form-hint">이미 진단을 끝냈어요. 결과 화면에서 아는 개념과 보충할 개념을 볼 수 있어요.</p>
        {restartBlocked && (
          <p className="diagnosis-restart-blocked" role="status">
            {RESTART_BLOCKED}
          </p>
        )}
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <div className="form">
          <button type="button" onClick={() => navigate('/result')}>
            결과 보기
          </button>
          {!restartBlocked && (
            <button type="button" className="secondary" onClick={handleRestart} disabled={loading}>
              {loading ? '불러오는 중…' : '다시 진단하기 (지금 결과는 지워져요)'}
            </button>
          )}
        </div>
      </section>
    )
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
          <button type="button" onClick={handleStart} disabled={loading || finished === null}>
            {loading || finished === null ? '불러오는 중…' : '진단 시작'}
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
        {/* 이번에 진단을 끝까지 푼 경우만 (이미 끝난 진단으로 들어오면 step이 없다) */}
        {step && !step.question && (
          <p className="diagnosis-reason" role="status">
            {finishReason({ answered: step.number, max: step.total, correct: correctCount })}
          </p>
        )}
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
        <span>{progressLabel(number, total)}</span>
        <progress value={number} max={total} aria-label={`진단 진행: ${progressLabel(number, total)}`} />
      </div>

      {reason && (
        <p className={`diagnosis-reason ${reason.tone}`} role="status">
          {reason.tone !== 'neutral' && (
            <span className="diagnosis-reason-icon" aria-hidden="true">
              {reason.tone === 'known' ? '✓' : '!'}
            </span>
          )}
          <span>{reason.text}</span>
        </p>
      )}

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
