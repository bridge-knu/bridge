// 코드 자동 저장 (개발 가이드 7장).
// - 타이핑이 멈추고 3초 뒤 PUT /code/{blockId} (디바운스)
// - 저장 요청은 한 번에 하나만 보낸다. 저장 중에 코드가 바뀌면 끝난 뒤 최신 코드로 다시 저장하므로
//   늦게 도착한 옛 요청이 새 코드를 덮어쓰는 역전이 생기지 않는다.
// - 실패하면 잠시 뒤 최신 코드로 다시 시도한다 (3초부터 최대 30초까지 늘림).
// - 브라우저 저장소(localStorage 등)에는 아무것도 남기지 않는다. 서버에만 저장한다.
// React와 무관한 순수 클래스라서 가짜 타이머로 테스트한다.

import { ApiError } from '../api.ts'

export const SAVE_DELAY_MS = 3000
export const RETRY_DELAYS_MS = [3000, 6000, 12000, 30000]

export type SaveStatus =
  /** 바뀐 내용 없음 (처음 연 상태 또는 저장 완료) */
  | 'saved'
  /** 바뀐 내용이 있고 3초 대기 중 */
  | 'pending'
  /** 저장 요청 중 */
  | 'saving'
  /** 실패, 잠시 뒤 다시 시도 */
  | 'retrying'
  /** 다시 시도해도 안 되는 실패 (4xx). 직접 다시 시도해야 함 */
  | 'failed'

export interface SaveState {
  status: SaveStatus
  /** 마지막으로 서버에 저장된 시각. 한 번도 없으면 null */
  savedAt: Date | null
  /** 서버에 아직 저장되지 않은 변경이 있는지 */
  dirty: boolean
  /** 실패 안내 (failed·retrying일 때) */
  error: string | null
}

export interface AutoSaverOptions {
  /** 실제 저장. 서버가 돌려준 저장 시각(ISO)을 돌려준다 */
  save: (code: string) => Promise<{ updatedAt: string }>
  onChange: (state: SaveState) => void
  /** 401: 토큰 만료 → 저장을 멈추고 알린다 */
  onUnauthorized?: () => void
  /** 서버에 저장되어 있던 코드와 시각 (GET /blocks/{id}의 savedCode·savedAt) */
  initialCode: string
  initialSavedAt?: string | null
  delayMs?: number
  retryDelaysMs?: number[]
}

function isRetryable(err: unknown): boolean {
  if (!(err instanceof ApiError)) return true // 네트워크 실패 등
  return err.status >= 500 || err.status === 408 || err.status === 429
}

function failMessage(err: unknown): string {
  if (err instanceof ApiError && err.detail) return err.detail
  if (err instanceof TypeError) return '서버에 연결할 수 없어요'
  return '저장하지 못했어요'
}

export class AutoSaver {
  private readonly opts: Required<Omit<AutoSaverOptions, 'onUnauthorized' | 'initialSavedAt'>> &
    Pick<AutoSaverOptions, 'onUnauthorized'>
  /** 에디터의 최신 코드 */
  private latest: string
  /** 서버에 저장된 것으로 확인된 코드 */
  private persisted: string
  private timer: ReturnType<typeof setTimeout> | null = null
  private inFlight: Promise<void> | null = null
  private retryIndex = 0
  private disposed = false
  private stopped = false
  private state: SaveState

  constructor(options: AutoSaverOptions) {
    this.opts = {
      save: options.save,
      onChange: options.onChange,
      onUnauthorized: options.onUnauthorized,
      initialCode: options.initialCode,
      delayMs: options.delayMs ?? SAVE_DELAY_MS,
      retryDelaysMs: options.retryDelaysMs ?? RETRY_DELAYS_MS,
    }
    this.latest = options.initialCode
    this.persisted = options.initialCode
    this.state = {
      status: 'saved',
      savedAt: options.initialSavedAt ? new Date(options.initialSavedAt) : null,
      dirty: false,
      error: null,
    }
  }

  getState(): SaveState {
    return this.state
  }

  /** 에디터 내용이 바뀔 때마다 부른다. 3초 동안 더 바뀌지 않으면 저장한다 */
  change(code: string): void {
    if (this.disposed || this.stopped) return
    this.latest = code
    if (code === this.persisted && !this.inFlight) {
      // 저장된 내용으로 되돌아옴 → 보낼 필요 없음
      this.clearTimer()
      this.retryIndex = 0
      this.update({ status: 'saved', dirty: false, error: null })
      return
    }
    // 재시도 대기 중이면 그 일정을 유지하되 최신 코드를 보낸다
    if (this.state.status === 'retrying' && this.timer) {
      this.update({ dirty: true })
      return
    }
    this.schedule(this.opts.delayMs)
    if (!this.inFlight) this.update({ status: 'pending', dirty: true, error: null })
    else this.update({ dirty: true })
  }

  /** 기다리지 않고 바로 저장한다 (페이지를 떠날 때, 블록 완료 전, "다시 시도" 버튼) */
  flush(): Promise<void> {
    if (this.disposed) return Promise.resolve()
    this.stopped = false
    this.clearTimer()
    return this.saveNow()
  }

  /** 타이머를 정리하고 이후 결과는 무시한다 (화면 상태도 더 바꾸지 않음) */
  dispose(): void {
    this.clearTimer()
    this.disposed = true
  }

  /**
   * 화면을 떠날 때 (다른 블록·페이지로 이동, unmount).
   * 저장되지 않은 최신 코드를 한 번 더 보내고 정리한다. 저장 중인 요청이 있으면 끝난 뒤 보낸다.
   * 결과는 기다리지 않는다 (화면이 이미 없으므로).
   */
  close(): void {
    if (this.disposed) return
    this.clearTimer()
    this.disposed = true
    if (this.stopped) return
    const sendLatest = () => {
      if (this.latest !== this.persisted) void this.opts.save(this.latest).catch(() => undefined)
    }
    if (this.inFlight) void this.inFlight.then(sendLatest)
    else sendLatest()
  }

  /** 서버에 아직 저장되지 않은 변경이 있는지 */
  hasUnsavedChanges(): boolean {
    return this.latest !== this.persisted
  }

  private schedule(ms: number): void {
    this.clearTimer()
    this.timer = setTimeout(() => {
      this.timer = null
      void this.saveNow()
    }, ms)
  }

  private clearTimer(): void {
    if (this.timer) clearTimeout(this.timer)
    this.timer = null
  }

  private async saveNow(): Promise<void> {
    // 이미 저장 중이면 끝난 뒤 최신 코드로 이어서 저장한다 (요청은 하나씩)
    if (this.inFlight) {
      await this.inFlight
      if (this.disposed || !this.hasUnsavedChanges()) return
      return this.saveNow()
    }
    if (!this.hasUnsavedChanges()) {
      this.update({ status: 'saved', dirty: false, error: null })
      return
    }

    const code = this.latest
    this.update({ status: 'saving', dirty: true })
    const run = (async () => {
      try {
        const res = await this.opts.save(code)
        this.persisted = code
        if (this.disposed) return
        this.retryIndex = 0
        const dirty = this.hasUnsavedChanges()
        this.update({
          status: dirty ? 'pending' : 'saved',
          savedAt: new Date(res.updatedAt),
          dirty,
          error: null,
        })
      } catch (err) {
        if (this.disposed) return
        if (err instanceof ApiError && err.status === 401) {
          this.stopped = true
          this.clearTimer()
          this.update({ status: 'failed', dirty: true, error: '다시 로그인해 주세요' })
          this.opts.onUnauthorized?.()
          return
        }
        if (isRetryable(err)) {
          const delays = this.opts.retryDelaysMs
          const wait = delays[Math.min(this.retryIndex, delays.length - 1)]
          this.retryIndex += 1
          this.update({ status: 'retrying', dirty: true, error: failMessage(err) })
          this.schedule(wait)
        } else {
          this.clearTimer()
          this.update({ status: 'failed', dirty: true, error: failMessage(err) })
        }
      }
    })()
    this.inFlight = run
    try {
      await run
    } finally {
      this.inFlight = null
    }
    // 저장 중에 바뀐 내용이 있으면 디바운스 후 이어서 저장 (실패 재시도는 위에서 이미 예약됨)
    if (!this.disposed && this.state.status === 'pending' && !this.timer) this.schedule(this.opts.delayMs)
  }

  private update(patch: Partial<SaveState>): void {
    this.state = { ...this.state, ...patch }
    if (!this.disposed) this.opts.onChange(this.state)
  }
}

/** "3초 전 저장됨" 같은 상태 문구 */
export function saveStatusText(state: SaveState, now: Date = new Date()): string {
  switch (state.status) {
    case 'pending':
      return '저장 대기 중…'
    case 'saving':
      return '저장 중…'
    case 'retrying':
      return '저장 안 됨 · 다시 시도 중'
    case 'failed':
      return `저장 안 됨${state.error ? ` · ${state.error}` : ''}`
    case 'saved':
      return state.savedAt ? `${elapsed(state.savedAt, now)} 저장됨` : '아직 저장한 코드 없음'
  }
}

function elapsed(at: Date, now: Date): string {
  const s = Math.max(0, Math.floor((now.getTime() - at.getTime()) / 1000))
  if (s < 1) return '방금'
  if (s < 60) return `${s}초 전`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}분 전`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}시간 전`
  return `${Math.floor(h / 24)}일 전`
}
