import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, type RunResult } from '../api.ts'
import { runOutcome, runOutcomeText, startRun, type RunPhase } from './runner.ts'

// 테스트용 결과. 모양은 backend/app/api/schemas.py의 RunResult와 mock(/run) 응답을 따른다.
const result = (over: Partial<RunResult> = {}): RunResult => ({
  jobId: 'job1',
  status: 'done',
  stdout: '15\n',
  stderr: '',
  exitCode: 0,
  timedOut: false,
  durationMs: 35,
  matchesExpected: true,
  ...over,
})

const REQ = { lang: 'c' as const, code: 'int main(void){}', blockId: 'b-array-1' }

function setup(pollResults: (RunResult | Error)[], runImpl?: () => Promise<{ jobId: string }>) {
  const phases: RunPhase[] = []
  const run = vi.fn(runImpl ?? (async () => ({ jobId: 'job1' })))
  let i = 0
  const poll = vi.fn(async () => {
    const r = pollResults[Math.min(i++, pollResults.length - 1)]
    if (r instanceof Error) throw r
    return r
  })
  const handle = startRun(REQ, { run, poll }, (p) => phases.push(p))
  return { phases, run, poll, handle, last: () => phases[phases.length - 1] }
}

beforeEach(() => {
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
})

describe('startRun', () => {
  it('POST /run에 코드·언어·blockId를 보내고 jobId로 0.5초마다 확인, done이면 멈춘다', async () => {
    const t = setup([result({ status: 'queued' }), result({ status: 'running' }), result()])
    await vi.advanceTimersByTimeAsync(0)
    expect(t.run).toHaveBeenCalledWith(REQ)
    expect(t.last()).toEqual({ kind: 'waiting', jobId: 'job1', status: 'queued' })
    expect(t.poll).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(499)
    expect(t.poll).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(t.poll).toHaveBeenCalledTimes(1)
    expect(t.poll).toHaveBeenLastCalledWith('job1')

    await vi.advanceTimersByTimeAsync(500)
    expect(t.poll).toHaveBeenCalledTimes(2)
    expect(t.last()).toEqual({ kind: 'waiting', jobId: 'job1', status: 'running' })

    await vi.advanceTimersByTimeAsync(500)
    expect(t.poll).toHaveBeenCalledTimes(3)
    expect(t.last()).toEqual({ kind: 'done', result: result() })

    // done 이후에는 더 부르지 않는다
    await vi.advanceTimersByTimeAsync(10_000)
    expect(t.poll).toHaveBeenCalledTimes(3)
    await t.handle.finished
  })

  it('응답이 느려도 요청이 겹치지 않는다 (앞 요청이 끝나고 0.5초 뒤)', async () => {
    let resolvePoll: (r: RunResult) => void = () => undefined
    const phases: RunPhase[] = []
    const poll = vi.fn(() => new Promise<RunResult>((r) => (resolvePoll = r)))
    startRun(REQ, { run: async () => ({ jobId: 'job1' }), poll }, (p) => phases.push(p))
    await vi.advanceTimersByTimeAsync(500)
    expect(poll).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(3000)
    expect(poll).toHaveBeenCalledTimes(1)
    resolvePoll(result({ status: 'running' }))
    await vi.advanceTimersByTimeAsync(500)
    expect(poll).toHaveBeenCalledTimes(2)
  })

  it('cancel하면 polling을 멈추고 더 알리지 않는다 (페이지 이동)', async () => {
    const t = setup([result({ status: 'running' })])
    await vi.advanceTimersByTimeAsync(1000)
    const calls = t.poll.mock.calls.length
    const phases = t.phases.length
    t.handle.cancel()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(t.poll.mock.calls.length).toBe(calls)
    expect(t.phases.length).toBe(phases)
    await t.handle.finished
  })

  it('실행 요청(POST) 실패는 requestFailed', async () => {
    const t = setup([], async () => {
      throw new ApiError(503, { detail: '잠시 후 다시 시도해 주세요', code: 'SERVICE_UNAVAILABLE' })
    })
    await vi.advanceTimersByTimeAsync(0)
    expect(t.last()).toEqual({ kind: 'requestFailed', message: '잠시 후 다시 시도해 주세요' })
    expect(t.poll).not.toHaveBeenCalled()
  })

  it('결과 확인(GET) 404는 바로 pollFailed', async () => {
    const t = setup([new ApiError(404, { detail: '실행 작업을 찾을 수 없어요', code: 'JOB_NOT_FOUND' })])
    await vi.advanceTimersByTimeAsync(500)
    expect(t.last()).toEqual({ kind: 'pollFailed', jobId: 'job1', message: '실행 작업을 찾을 수 없어요' })
    await vi.advanceTimersByTimeAsync(5000)
    expect(t.poll).toHaveBeenCalledTimes(1)
  })

  it('네트워크 실패는 3번 연속이면 pollFailed, 그 전에 성공하면 계속', async () => {
    const net = new TypeError('Failed to fetch')
    const ok = setup([net, net, result()])
    await vi.advanceTimersByTimeAsync(1500)
    expect(ok.last()).toEqual({ kind: 'done', result: result() })

    const fail = setup([net, net, net, result()])
    await vi.advanceTimersByTimeAsync(1500)
    expect(fail.last()).toMatchObject({ kind: 'pollFailed', jobId: 'job1' })
    await vi.advanceTimersByTimeAsync(5000)
    expect(fail.poll).toHaveBeenCalledTimes(3)
  })

  it('401이면 unauthorized로 멈춘다', async () => {
    const t = setup([new ApiError(401, { detail: 'x', code: 'UNAUTHORIZED' })])
    await vi.advanceTimersByTimeAsync(500)
    expect(t.last()).toEqual({ kind: 'unauthorized' })
    await vi.advanceTimersByTimeAsync(5000)
    expect(t.poll).toHaveBeenCalledTimes(1)
  })

  it('최대 대기 시간이 지나면 멈춘다 (무한 polling 없음)', async () => {
    const phases: RunPhase[] = []
    const poll = vi.fn(async () => result({ status: 'running' }))
    startRun(REQ, { run: async () => ({ jobId: 'job1' }), poll, maxWaitMs: 3000 }, (p) => phases.push(p))
    await vi.advanceTimersByTimeAsync(10_000)
    expect(phases[phases.length - 1]).toMatchObject({ kind: 'pollFailed' })
    expect(poll.mock.calls.length).toBeLessThanOrEqual(6)
    const n = poll.mock.calls.length
    await vi.advanceTimersByTimeAsync(10_000)
    expect(poll.mock.calls.length).toBe(n)
  })
})

describe('runOutcome', () => {
  it('정상 종료 + 정답 출력과 같음 → success', () => {
    expect(runOutcome(result(), 'c')).toBe('success')
    expect(runOutcome(result({ matchesExpected: null }), 'c')).toBe('success')
  })

  it('정상 종료 + 정답 출력과 다름 → wrongOutput', () => {
    expect(runOutcome(result({ stdout: '0\n', matchesExpected: false }), 'c')).toBe('wrongOutput')
  })

  it('mock 컴파일 에러 응답 → compileError', () => {
    const r = result({
      stdout: '',
      stderr: "main.c:3:5: error: expected ';' before 'return'",
      exitCode: 1,
      durationMs: 120,
      matchesExpected: false,
    })
    expect(runOutcome(r, 'c')).toBe('compileError')
    expect(runOutcomeText('compileError')).toBe('컴파일 오류')
  })

  it('경고 뒤 에러가 나와도 compileError', () => {
    const stderr = "main.c: In function 'main':\nmain.c:4:5: warning: unused\nmain.c:5:1: error: expected '}'"
    expect(runOutcome(result({ stdout: '', stderr, exitCode: 1 }), 'c')).toBe('compileError')
  })

  it('mock 시간 초과 응답 → timeout', () => {
    const r = result({ stdout: '', stderr: '시간 초과 (5초)', exitCode: 124, timedOut: true, matchesExpected: false })
    expect(runOutcome(r, 'c')).toBe('timeout')
    expect(runOutcomeText('timeout')).toBe('시간 초과')
  })

  it('segfault 등 실행 중 비정상 종료 → runtimeError', () => {
    const r = result({ stdout: '1\n', stderr: '잘못된 메모리 접근 (Segmentation fault)', exitCode: 139, matchesExpected: false })
    expect(runOutcome(r, 'c')).toBe('runtimeError')
    expect(runOutcome(result({ stdout: '', stderr: 'Traceback ...', exitCode: 1 }), 'python')).toBe('runtimeError')
  })
})
