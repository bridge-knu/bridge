// 코드 실행 (개발 가이드 7장). 실행은 백엔드 샌드박스가 하고, 여기서는 요청과 결과 확인만 한다.
// 1. POST /run → jobId
// 2. GET /run/{jobId}를 0.5초마다 (앞 요청이 끝난 뒤 0.5초. 응답이 느려도 요청이 겹치지 않음)
// 3. status가 done이면 멈추고 결과를 넘긴다
// 실패·취소·최대 대기 시간 초과에도 반드시 멈춘다 (무한 polling 없음).

import { ApiError, type RunRequest, type RunResult } from '../api.ts'

export const POLL_INTERVAL_MS = 500
/** 이 시간이 지나도 done이 아니면 멈춘다. 백엔드(#39)는 90초가 지난 작업을 실패로 돌려준다 */
export const MAX_WAIT_MS = 120_000
/** GET /run 이 연달아 이만큼 실패하면 멈춘다 (네트워크 순간 끊김은 견딤) */
export const MAX_POLL_FAILURES = 3

export type RunPhase =
  | { kind: 'requesting' }
  | { kind: 'waiting'; jobId: string; status: 'queued' | 'running' }
  | { kind: 'done'; result: RunResult }
  /** POST /run 실패 */
  | { kind: 'requestFailed'; message: string }
  /** GET /run/{jobId} 실패 또는 최대 대기 시간 초과 */
  | { kind: 'pollFailed'; jobId: string; message: string }
  | { kind: 'unauthorized' }

export interface RunDeps {
  run: (req: RunRequest) => Promise<{ jobId: string }>
  poll: (jobId: string) => Promise<RunResult>
  intervalMs?: number
  maxWaitMs?: number
  maxPollFailures?: number
  now?: () => number
}

export interface RunHandle {
  /** polling을 멈춘다 (페이지를 떠날 때). 이후 콜백은 부르지 않는다 */
  cancel: () => void
  /** 끝(done·실패·취소)나면 resolve */
  finished: Promise<void>
}

function message(err: unknown, fallback: string): string {
  if (err instanceof ApiError && err.detail) return err.detail
  if (err instanceof TypeError) return '서버에 연결할 수 없어요. 네트워크를 확인해 주세요'
  return fallback
}

export function startRun(req: RunRequest, deps: RunDeps, onPhase: (phase: RunPhase) => void): RunHandle {
  const interval = deps.intervalMs ?? POLL_INTERVAL_MS
  const maxWait = deps.maxWaitMs ?? MAX_WAIT_MS
  const maxFailures = deps.maxPollFailures ?? MAX_POLL_FAILURES
  const now = deps.now ?? (() => Date.now())

  let cancelled = false
  let timer: ReturnType<typeof setTimeout> | null = null
  let resolveFinished: () => void = () => undefined
  const finished = new Promise<void>((resolve) => {
    resolveFinished = resolve
  })

  const emit = (phase: RunPhase) => {
    if (!cancelled) onPhase(phase)
  }
  const finish = () => {
    if (timer) clearTimeout(timer)
    timer = null
    resolveFinished()
  }
  const wait = () =>
    new Promise<void>((resolve) => {
      timer = setTimeout(() => {
        timer = null
        resolve()
      }, interval)
    })

  void (async () => {
    emit({ kind: 'requesting' })
    let jobId: string
    try {
      jobId = (await deps.run(req)).jobId
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) emit({ kind: 'unauthorized' })
      else emit({ kind: 'requestFailed', message: message(err, '실행을 요청하지 못했어요. 다시 시도해 주세요') })
      return finish()
    }
    if (cancelled) return finish()
    emit({ kind: 'waiting', jobId, status: 'queued' })

    const startedAt = now()
    let failures = 0
    for (;;) {
      await wait()
      if (cancelled) return finish()
      if (now() - startedAt > maxWait) {
        emit({ kind: 'pollFailed', jobId, message: '실행 결과가 너무 늦어요. 다시 실행해 주세요' })
        return finish()
      }
      try {
        const result = await deps.poll(jobId)
        if (cancelled) return finish()
        failures = 0
        if (result.status === 'done') {
          emit({ kind: 'done', result })
          return finish()
        }
        emit({ kind: 'waiting', jobId, status: result.status })
      } catch (err) {
        if (cancelled) return finish()
        if (err instanceof ApiError && err.status === 401) {
          emit({ kind: 'unauthorized' })
          return finish()
        }
        failures += 1
        // 없는 작업(404)은 기다려도 생기지 않는다
        if ((err instanceof ApiError && err.status === 404) || failures >= maxFailures) {
          emit({ kind: 'pollFailed', jobId, message: message(err, '실행 결과를 가져오지 못했어요') })
          return finish()
        }
      }
    }
  })()

  return {
    cancel() {
      cancelled = true
      finish()
    },
    finished,
  }
}

/** 실행 결과 종류 */
export type RunOutcome =
  /** 정상 종료, 정답 출력과 같음 (또는 비교 대상 없음) */
  | 'success'
  /** 정상 종료, 정답 출력과 다름 */
  | 'wrongOutput'
  | 'compileError'
  | 'runtimeError'
  | 'timeout'

// gcc 진단 형식 "main.c:3:5: error: ...". RunResult에 컴파일/실행 단계 구분 필드가 없어서
// stderr로 구분한다 (sandbox/runner.py는 gcc main.c로 컴파일하고 그 stderr를 그대로 돌려줌).
const GCC_ERROR = /^main\.c:\d+(?::\d+)?: (?:fatal )?error:/m

export function runOutcome(result: RunResult, lang: RunRequest['lang']): RunOutcome {
  if (result.timedOut) return 'timeout'
  if (result.exitCode === 0) return result.matchesExpected === false ? 'wrongOutput' : 'success'
  if (lang === 'c' && result.stdout === '' && GCC_ERROR.test(result.stderr)) return 'compileError'
  return 'runtimeError'
}

export function runOutcomeText(outcome: RunOutcome): string {
  switch (outcome) {
    case 'success':
      return '실행 성공'
    case 'wrongOutput':
      return '실행은 됐지만 정답 출력과 달라요'
    case 'compileError':
      return '컴파일 오류'
    case 'runtimeError':
      return '실행 중 오류'
    case 'timeout':
      return '시간 초과'
  }
}
