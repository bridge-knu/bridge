import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  completeBlock,
  getBlock,
  getRunResult,
  runCode,
  saveCode,
  setAuthToken,
  type BlockDetail,
  type CompleteResponse,
} from '../api.ts'
import { AutoSaver, saveStatusText, type SaveState } from '../block/autosave.ts'
import { runOutcome, runOutcomeText, startRun, type RunHandle, type RunPhase } from '../block/runner.ts'
import { embedUrl, formatSeconds } from '../block/video.ts'
import { classifyBlockError, editorLanguage, errorText, initialCode, toCheckAnswers } from '../block/view.ts'

// Monaco는 크기가 커서 블록 화면에 들어올 때만 불러온다.
const CodeEditor = lazy(() => import('../block/CodeEditor.tsx'))

type LoadState =
  | { status: 'loading' }
  | { status: 'notFound'; message: string }
  | { status: 'error'; message: string }
  | { status: 'ready'; block: BlockDetail }

export default function BlockPage() {
  const { blockId = '' } = useParams()
  // 블록이 바뀌면 화면 상태(에디터·자동 저장·실행)를 통째로 새로 만든다.
  return <BlockLoader key={blockId} blockId={blockId} />
}

function useLogout() {
  const navigate = useNavigate()
  return useCallback(() => {
    // 토큰이 없거나 만료됨 (새로고침하면 메모리 토큰이 사라짐) → 다시 로그인
    setAuthToken(null)
    navigate('/login', { replace: true })
  }, [navigate])
}

function BlockLoader({ blockId }: { blockId: string }) {
  const logout = useLogout()
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading' })
    getBlock(blockId)
      .then((block) => {
        if (!cancelled) setState({ status: 'ready', block })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const kind = classifyBlockError(err)
        if (kind === 'unauthorized') return logout()
        if (kind === 'notFound') setState({ status: 'notFound', message: errorText(err, '블록을 찾을 수 없어요') })
        else setState({ status: 'error', message: errorText(err, '블록을 불러오지 못했어요. 다시 시도해 주세요') })
      })
    return () => {
      cancelled = true
    }
  }, [blockId, logout, reloadKey])

  if (state.status === 'loading') {
    return (
      <section>
        <h1>블록 학습</h1>
        <p className="form-hint" role="status">
          블록을 불러오는 중…
        </p>
      </section>
    )
  }

  if (state.status === 'notFound' || state.status === 'error') {
    return (
      <section className="form-page">
        <h1>블록 학습</h1>
        <p className="form-error" role="alert">
          {state.message}
        </p>
        <div className="form">
          {state.status === 'error' && (
            <button type="button" onClick={() => setReloadKey((k) => k + 1)}>
              다시 불러오기
            </button>
          )}
          <Link to="/plan" className="block-link-button">
            플랜으로 돌아가기
          </Link>
        </div>
      </section>
    )
  }

  return <BlockView block={state.block} onUnauthorized={logout} />
}

function VideoSection({ block }: { block: BlockDetail }) {
  const src = embedUrl(block.video)
  return (
    <section className="block-section" aria-labelledby="block-video-title">
      <h2 id="block-video-title">강의</h2>
      {src ? (
        <>
          <div className="block-video">
            <iframe
              src={src}
              title={`${block.conceptName} 강의`}
              allow="accelerometer; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
              referrerPolicy="strict-origin-when-cross-origin"
            />
          </div>
          <p className="form-hint">
            재생 구간 {formatSeconds(block.video.start)} ~ {formatSeconds(block.video.end)}
          </p>
        </>
      ) : (
        <p className="form-hint">이 블록에는 볼 수 있는 강의 영상이 없어요. 아래 실습부터 진행해 주세요.</p>
      )}
    </section>
  )
}

function useAutoSave(block: BlockDetail, onUnauthorized: () => void) {
  const saverRef = useRef<AutoSaver | null>(null)
  const [saveState, setSaveState] = useState<SaveState>({
    status: 'saved',
    savedAt: block.savedAt ? new Date(block.savedAt) : null,
    dirty: false,
    error: null,
  })

  useEffect(() => {
    const saver = new AutoSaver({
      save: (code) => saveCode(block.id, code),
      onChange: setSaveState,
      onUnauthorized,
      initialCode: initialCode(block),
      initialSavedAt: block.savedAt,
    })
    saverRef.current = saver

    // 새로고침·탭 닫기: 저장 안 된 변경이 있으면 바로 보내고 브라우저 확인 창을 띄운다
    const beforeUnload = (e: BeforeUnloadEvent) => {
      if (!saver.hasUnsavedChanges()) return
      void saver.flush()
      e.preventDefault()
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => {
      window.removeEventListener('beforeunload', beforeUnload)
      // 다른 블록·페이지로 이동: 남은 변경을 보내고 타이머 정리
      saver.close()
      saverRef.current = null
    }
  }, [block, onUnauthorized])

  // "3초 전 저장됨" 문구를 1초마다 새로 그린다
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  return { saverRef, saveState, now }
}

function RunResultView({ phase, lang }: { phase: RunPhase | null; lang: BlockDetail['practice']['lang'] }) {
  if (!phase) return <p className="form-hint">실행 버튼을 누르면 결과가 여기에 나와요.</p>
  switch (phase.kind) {
    case 'requesting':
      return <p className="run-status running">실행 요청 중…</p>
    case 'waiting':
      return <p className="run-status running">{phase.status === 'queued' ? '실행 대기 중…' : '실행 중…'}</p>
    case 'requestFailed':
      return <p className="run-status error">실행 요청 실패 · {phase.message}</p>
    case 'pollFailed':
      return <p className="run-status error">결과 확인 실패 · {phase.message}</p>
    case 'unauthorized':
      return null
    case 'done': {
      const r = phase.result
      const outcome = runOutcome(r, lang)
      return (
        <div className="run-result">
          <p className={`run-status ${outcome === 'success' ? 'success' : 'error'}`}>
            {runOutcomeText(outcome)}
            {r.matchesExpected === true && ' · 정답 출력과 같아요'}
            <span className="run-meta">
              {r.exitCode !== null && ` 종료 코드 ${r.exitCode}`}
              {r.durationMs !== null && ` · ${r.durationMs}ms`}
            </span>
          </p>
          <h3>표준 출력</h3>
          <pre className="run-output">{r.stdout || '(출력 없음)'}</pre>
          {r.stderr && (
            <>
              <h3>{outcome === 'compileError' ? '컴파일 메시지' : '에러'}</h3>
              <pre className="run-output stderr">{r.stderr}</pre>
            </>
          )}
        </div>
      )
    }
  }
}

function BlockView({ block, onUnauthorized }: { block: BlockDetail; onUnauthorized: () => void }) {
  const { saverRef, saveState, now } = useAutoSave(block, onUnauthorized)
  const codeRef = useRef(initialCode(block))

  // ---- 실행 ----
  const [runPhase, setRunPhase] = useState<RunPhase | null>(null)
  const runRef = useRef<RunHandle | null>(null)
  const running = runPhase?.kind === 'requesting' || runPhase?.kind === 'waiting'

  useEffect(() => {
    // 페이지를 떠나면 polling을 멈춘다
    return () => runRef.current?.cancel()
  }, [])

  function handleRun() {
    if (runRef.current) return
    runRef.current = startRun(
      { lang: block.practice.lang, code: codeRef.current, blockId: block.id },
      { run: runCode, poll: getRunResult },
      (phase) => {
        setRunPhase(phase)
        if (phase.kind === 'unauthorized') onUnauthorized()
      },
    )
    void runRef.current.finished.then(() => {
      runRef.current = null
    })
  }

  // ---- 확인 문제·완료 ----
  const [selected, setSelected] = useState<Record<string, number | undefined>>({})
  const [completing, setCompleting] = useState(false)
  const [completeResult, setCompleteResult] = useState<CompleteResponse | null>(null)
  const [completeError, setCompleteError] = useState<string | null>(null)
  const completingRef = useRef(false)
  const done = completeResult?.done ?? block.done
  const questions = block.checkQuestions
  const unanswered = questions.filter((q) => selected[q.id] === undefined).length

  async function handleComplete() {
    if (completingRef.current) return
    completingRef.current = true
    setCompleting(true)
    setCompleteError(null)
    try {
      // 완료 전에 코드부터 저장해 둔다 (실패해도 완료는 진행)
      await saverRef.current?.flush().catch(() => undefined)
      const res = await completeBlock(block.id, {
        checkAnswers: toCheckAnswers(
          questions.map((q) => q.id),
          selected,
        ),
      })
      setCompleteResult(res)
    } catch (err) {
      if (classifyBlockError(err) === 'unauthorized') return onUnauthorized()
      setCompleteError(errorText(err, '완료 처리에 실패했어요. 다시 시도해 주세요'))
    } finally {
      completingRef.current = false
      setCompleting(false)
    }
  }

  const saveText = saveStatusText(saveState, now)
  const saveClass = saveState.status === 'retrying' || saveState.status === 'failed' ? 'error' : saveState.status

  return (
    <article className="block-page">
      <header className="block-header">
        <h1>
          {block.conceptName}
          {done && <span className="block-badge done">완료</span>}
        </h1>
        <p className="form-hint">
          {block.minutes}분 블록 · 강의 보기 → 실습 코드 실행 → 확인 문제 순서로 진행해요
        </p>
      </header>

      <VideoSection block={block} />

      <section className="block-section" aria-labelledby="block-practice-title">
        <div className="block-section-head">
          <h2 id="block-practice-title">실습 ({block.practice.lang === 'c' ? 'C' : 'Python'})</h2>
          <span className={`save-status ${saveClass}`} role="status">
            {saveText}
            {saveState.dirty && saveState.status !== 'saving' && saveState.status !== 'pending' && ' · 저장 안 된 변경 있음'}
          </span>
        </div>
        <div className="block-editor">
          <Suspense fallback={<p className="form-hint">에디터 불러오는 중…</p>}>
            <CodeEditor
              defaultValue={codeRef.current}
              language={editorLanguage(block.practice.lang)}
              onChange={(code) => {
                codeRef.current = code
                saverRef.current?.change(code)
              }}
            />
          </Suspense>
        </div>
        <div className="block-toolbar">
          <button type="button" className="block-button" onClick={handleRun} disabled={running}>
            {running ? '실행 중…' : '실행'}
          </button>
          {(saveState.status === 'failed' || saveState.status === 'retrying') && (
            <button type="button" className="block-button secondary" onClick={() => void saverRef.current?.flush()}>
              지금 저장
            </button>
          )}
        </div>
        <details className="block-expected">
          <summary>목표 출력 보기</summary>
          <pre className="run-output">{block.practice.expected}</pre>
        </details>
        <div className="block-run" aria-live="polite">
          <RunResultView phase={runPhase} lang={block.practice.lang} />
        </div>
      </section>

      <section className="block-section" aria-labelledby="block-check-title">
        <h2 id="block-check-title">확인 문제</h2>
        {questions.length === 0 ? (
          <p className="form-hint">이 블록에는 확인 문제가 없어요.</p>
        ) : (
          <ol className="check-questions">
            {questions.map((q, qi) => (
              <li key={q.id}>
                <fieldset disabled={completing}>
                  <legend>
                    {qi + 1}. {q.prompt}
                  </legend>
                  {q.code && (
                    <pre className="diagnosis-code">
                      <code>{q.code}</code>
                    </pre>
                  )}
                  <div className="check-choices">
                    {q.choices.map((choice, i) => (
                      <label key={`${q.id}-${i}`} className={selected[q.id] === i ? 'selected' : undefined}>
                        <input
                          type="radio"
                          name={q.id}
                          checked={selected[q.id] === i}
                          onChange={() => setSelected((s) => ({ ...s, [q.id]: i }))}
                        />
                        {choice}
                      </label>
                    ))}
                  </div>
                </fieldset>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="block-section block-complete">
        {completeResult && (
          <p className="run-status success" role="status">
            블록을 완료했어요
            {completeResult.totalCount > 0 &&
              ` · 확인 문제 ${completeResult.totalCount}개 중 ${completeResult.correctCount}개 정답`}
          </p>
        )}
        {completeError && (
          <p className="form-error" role="alert">
            {completeError}
          </p>
        )}
        {!completeResult && unanswered > 0 && (
          <p className="form-hint">답하지 않은 문제 {unanswered}개는 틀린 것으로 채점돼요.</p>
        )}
        <div className="block-toolbar">
          <button type="button" className="block-button" onClick={handleComplete} disabled={completing}>
            {completing ? '완료 처리 중…' : done ? '확인 문제 다시 제출' : '블록 완료'}
          </button>
          {completeResult?.nextBlockId && (
            <Link to={`/blocks/${encodeURIComponent(completeResult.nextBlockId)}`} className="block-link-button">
              다음 블록으로
            </Link>
          )}
          <Link to="/plan" className="block-link-button secondary">
            플랜으로
          </Link>
        </div>
      </section>
    </article>
  )
}
