import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { generatePlan, getPlan, setAuthToken, type Plan } from '../api.ts'
import {
  classifyPlanError,
  formatDate,
  planErrorMessage,
  todayGuideText,
  toPlanView,
  type PlanDayView,
  type PlanView,
} from '../plan/view.ts'

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; plan: Plan }

function DayCard({ day, view }: { day: PlanDayView; view: PlanView }) {
  return (
    <section className={`plan-day${day.isToday ? ' today' : ''}`} aria-label={formatDate(day.date)}>
      <header className="plan-day-header">
        <h2>
          {day.isToday && <span className="plan-badge today">오늘</span>}
          {day.isPast && !day.allDone && <span className="plan-badge past">지난 날</span>}
          {formatDate(day.date)}
        </h2>
        <span className="plan-day-meta">
          {day.allDone ? '모두 완료' : `${day.blocks.length}개 · ${day.minutes}분`}
        </span>
      </header>
      <ol className="plan-blocks">
        {day.blocks.map((b) => {
          const reachable = view.reachableToday.has(b.blockId)
          const last = view.today.kind === 'remaining' && view.today.lastBlockId === b.blockId
          const cls = ['plan-block', b.done ? 'done' : '', reachable ? 'reachable' : ''].filter(Boolean).join(' ')
          return (
            <li key={b.blockId}>
              <Link to={`/blocks/${encodeURIComponent(b.blockId)}`} className={cls}>
                <span className="plan-block-name">{b.conceptName}</span>
                <span className="plan-block-meta">
                  {b.minutes}분
                  {b.done && <span className="plan-badge done">완료</span>}
                  {last && <span className="plan-badge until">여기까지 가능</span>}
                </span>
              </Link>
            </li>
          )
        })}
      </ol>
    </section>
  )
}

export default function PlanPage() {
  const navigate = useNavigate()
  const [state, setState] = useState<State>({ status: 'loading' })
  const [reloadKey, setReloadKey] = useState(0)
  const [generating, setGenerating] = useState(false)
  const [generateError, setGenerateError] = useState<string | null>(null)
  // 같은 틱에 두 번 눌러도 생성 요청이 한 번만 나가게 한다 (generating state는 다음 렌더에야 반영됨).
  const inFlight = useRef(false)

  // 오류 처리 공통. 401이면 로그인 화면으로 보내고 null, 그 밖에는 안내 문구를 돌려준다.
  const handleError = useCallback(
    (err: unknown): string | null => {
      // 토큰이 없거나 만료됨 (새로고침하면 메모리 토큰이 사라짐) → 다시 로그인
      if (classifyPlanError(err) === 'unauthorized') {
        setAuthToken(null)
        navigate('/login', { replace: true })
        return null
      }
      return planErrorMessage(err)
    },
    [navigate],
  )

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading' })
    getPlan()
      .then((plan) => {
        if (!cancelled) setState({ status: 'ready', plan })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const message = handleError(err)
        if (message) setState({ status: 'error', message })
      })
    return () => {
      cancelled = true
    }
  }, [handleError, reloadKey])

  async function handleGenerate() {
    if (inFlight.current) return
    inFlight.current = true
    setGenerating(true)
    setGenerateError(null)
    try {
      const plan = await generatePlan()
      setState({ status: 'ready', plan })
    } catch (err) {
      const message = handleError(err)
      if (message) setGenerateError(message)
    } finally {
      inFlight.current = false
      setGenerating(false)
    }
  }

  const view = useMemo(
    () => (state.status === 'ready' ? toPlanView(state.plan) : null),
    [state],
  )

  if (state.status === 'loading') {
    return (
      <section>
        <h1>학습 플랜</h1>
        <p className="form-hint" role="status">
          플랜을 불러오는 중…
        </p>
      </section>
    )
  }

  if (state.status === 'error') {
    return (
      <section className="form-page">
        <h1>학습 플랜</h1>
        <p className="form-error" role="alert">
          {state.message}
        </p>
        <div className="form">
          <button type="button" onClick={() => setReloadKey((k) => k + 1)}>
            다시 불러오기
          </button>
        </div>
      </section>
    )
  }

  const generateButton = (label: string) => (
    <button type="button" onClick={handleGenerate} disabled={generating}>
      {generating ? '플랜 만드는 중…' : label}
    </button>
  )

  if (!view || view.totalBlocks === 0) {
    return (
      <section className="form-page">
        <h1>학습 플랜</h1>
        <p className="form-hint">아직 플랜이 없어요. 진단을 끝냈다면 복학일까지의 플랜을 만들어 보세요.</p>
        {generateError && (
          <p className="form-error" role="alert">
            {generateError}
          </p>
        )}
        <div className="form">
          {generateButton('플랜 만들기')}
          <button type="button" className="secondary" onClick={() => navigate('/diagnosis')}>
            진단하러 가기
          </button>
        </div>
      </section>
    )
  }

  return (
    <section className="plan">
      <div className="plan-head">
        <div>
          <h1>학습 플랜</h1>
          <p className="form-hint">
            오늘 {formatDate(view.todayDate)} · 복학일 {formatDate(view.returnDate)}까지 · 하루 {view.dailyMinutes}분 · 블록 {view.doneBlocks}/
            {view.totalBlocks}개 완료
          </p>
        </div>
        <div className="form plan-actions">{generateButton('플랜 다시 만들기')}</div>
      </div>

      {generateError && (
        <p className="form-error" role="alert">
          {generateError}
        </p>
      )}

      <p className={`plan-guide ${view.allDone ? 'done' : view.today.kind}`} role="status">
        {view.allDone ? '플랜의 모든 블록을 끝냈어요. 복학 준비 완료!' : todayGuideText(view.today)}
      </p>

      <div className="plan-days">
        {view.days.map((day) => (
          <DayCard key={day.date} day={day} view={view} />
        ))}
      </div>

      {view.deferred !== null && (
        <section className="plan-deferred" aria-label="미룬 개념">
          <h2>복학 후로 미룬 개념</h2>
          {view.deferred.length === 0 ? (
            <p className="form-hint">시간 안에 모든 개념을 배울 수 있어요. 미룬 개념이 없어요.</p>
          ) : (
            <>
              <p className="form-hint">{view.message ?? '복학일까지 시간이 부족해 아래 개념은 플랜에서 뺐어요.'}</p>
              <ul>
                {view.deferred.map((c) => (
                  <li key={c.conceptId}>
                    {c.conceptName} <span className="plan-day-meta">블록 {c.blocks}개</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}
    </section>
  )
}
