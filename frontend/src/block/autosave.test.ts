import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api.ts'
import { AutoSaver, saveStatusText, type SaveState } from './autosave.ts'

// 테스트용 가짜 저장 함수. 호출마다 직접 resolve/reject 한다.
function fakeSave() {
  const calls: { code: string; resolve: (at: string) => void; reject: (e: unknown) => void }[] = []
  const save = vi.fn(
    (code: string) =>
      new Promise<{ updatedAt: string }>((resolve, reject) => {
        calls.push({ code, resolve: (updatedAt) => resolve({ updatedAt }), reject })
      }),
  )
  return { save, calls }
}

function setup(initialCode = 'start') {
  const fake = fakeSave()
  const states: SaveState[] = []
  const onUnauthorized = vi.fn()
  const saver = new AutoSaver({
    save: fake.save,
    onChange: (s) => states.push(s),
    onUnauthorized,
    initialCode,
  })
  const last = () => states[states.length - 1]
  return { ...fake, saver, states, last, onUnauthorized }
}

// 대기 중인 마이크로태스크(Promise then)를 흘려보낸다
const flushPromises = () => vi.advanceTimersByTimeAsync(0)

beforeEach(() => {
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
})

describe('AutoSaver: 3초 디바운스', () => {
  it('타이핑이 멈추고 3초 뒤에 한 번 저장한다', async () => {
    const t = setup()
    t.saver.change('a')
    expect(t.last().status).toBe('pending')
    await vi.advanceTimersByTimeAsync(2999)
    expect(t.save).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(t.save).toHaveBeenCalledTimes(1)
    expect(t.save).toHaveBeenLastCalledWith('a')
    expect(t.last().status).toBe('saving')

    t.calls[0].resolve('2026-11-21T00:00:03Z')
    await flushPromises()
    expect(t.last()).toMatchObject({ status: 'saved', dirty: false, savedAt: new Date('2026-11-21T00:00:03Z') })
  })

  it('연속 입력은 마지막 입력 3초 뒤 최신 코드로 한 번만 저장한다', async () => {
    const t = setup()
    for (const code of ['a', 'ab', 'abc', 'abcd']) {
      t.saver.change(code)
      await vi.advanceTimersByTimeAsync(1000)
    }
    expect(t.save).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(2000)
    expect(t.save).toHaveBeenCalledTimes(1)
    expect(t.save).toHaveBeenLastCalledWith('abcd')
  })

  it('저장된 내용으로 되돌리면 보내지 않는다', async () => {
    const t = setup('start')
    t.saver.change('x')
    t.saver.change('start')
    await vi.advanceTimersByTimeAsync(5000)
    expect(t.save).not.toHaveBeenCalled()
    expect(t.last()).toMatchObject({ status: 'saved', dirty: false })
  })
})

describe('AutoSaver: 요청 순서', () => {
  it('저장 중에 바뀐 코드는 앞 요청이 끝난 뒤 이어서 저장한다 (겹치거나 역전되지 않음)', async () => {
    const t = setup()
    t.saver.change('v1')
    await vi.advanceTimersByTimeAsync(3000)
    expect(t.save).toHaveBeenCalledTimes(1)

    // v1 저장이 끝나기 전에 v2 입력, 3초가 지나도 앞 요청이 안 끝났으면 새 요청을 보내지 않는다
    t.saver.change('v2')
    await vi.advanceTimersByTimeAsync(3000)
    expect(t.save).toHaveBeenCalledTimes(1)

    t.calls[0].resolve('2026-11-21T00:00:01Z')
    await flushPromises()
    expect(t.save).toHaveBeenCalledTimes(2)
    expect(t.save).toHaveBeenLastCalledWith('v2')

    t.calls[1].resolve('2026-11-21T00:00:02Z')
    await flushPromises()
    expect(t.last()).toMatchObject({ status: 'saved', dirty: false })
    // 더 보낼 게 없다
    await vi.advanceTimersByTimeAsync(10_000)
    expect(t.save).toHaveBeenCalledTimes(2)
  })

  it('저장 중 입력이 앞 요청보다 늦게 끝나도 디바운스 후 최신 코드로 저장한다', async () => {
    const t = setup()
    t.saver.change('v1')
    await vi.advanceTimersByTimeAsync(3000)
    t.saver.change('v2')
    t.calls[0].resolve('2026-11-21T00:00:01Z')
    await flushPromises()
    // v2 입력 후 아직 3초가 안 됐으면 기다린다
    expect(t.save).toHaveBeenCalledTimes(1)
    expect(t.last()).toMatchObject({ status: 'pending', dirty: true })
    await vi.advanceTimersByTimeAsync(3000)
    expect(t.save).toHaveBeenCalledTimes(2)
    expect(t.save).toHaveBeenLastCalledWith('v2')
  })
})

describe('AutoSaver: 실패와 재시도', () => {
  it('네트워크 실패 → "다시 시도 중", 3초 뒤 최신 코드로 다시 저장', async () => {
    const t = setup()
    t.saver.change('a')
    await vi.advanceTimersByTimeAsync(3000)
    t.calls[0].reject(new TypeError('Failed to fetch'))
    await flushPromises()
    expect(t.last()).toMatchObject({ status: 'retrying', dirty: true })
    expect(saveStatusText(t.last())).toBe('저장 안 됨 · 다시 시도 중')

    t.saver.change('ab') // 재시도 대기 중 입력 → 재시도 일정은 그대로, 최신 코드 전송
    await vi.advanceTimersByTimeAsync(3000)
    expect(t.save).toHaveBeenCalledTimes(2)
    expect(t.save).toHaveBeenLastCalledWith('ab')
    t.calls[1].resolve('2026-11-21T00:00:09Z')
    await flushPromises()
    expect(t.last()).toMatchObject({ status: 'saved', dirty: false })
  })

  it('계속 실패하면 재시도 간격을 늘린다 (3초 → 6초)', async () => {
    const t = setup()
    t.saver.change('a')
    await vi.advanceTimersByTimeAsync(3000)
    t.calls[0].reject(new ApiError(503, { detail: '잠시 후 다시 시도해 주세요', code: 'SERVICE_UNAVAILABLE' }))
    await vi.advanceTimersByTimeAsync(3000)
    expect(t.save).toHaveBeenCalledTimes(2)
    t.calls[1].reject(new ApiError(503, { detail: 'x' }))
    await vi.advanceTimersByTimeAsync(5999)
    expect(t.save).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(1)
    expect(t.save).toHaveBeenCalledTimes(3)
  })

  it('4xx(422 등)는 자동 재시도하지 않고 failed, flush로 다시 시도할 수 있다', async () => {
    const t = setup()
    t.saver.change('a')
    await vi.advanceTimersByTimeAsync(3000)
    t.calls[0].reject(new ApiError(422, { detail: [] }))
    await flushPromises()
    expect(t.last()).toMatchObject({ status: 'failed', dirty: true })
    await vi.advanceTimersByTimeAsync(60_000)
    expect(t.save).toHaveBeenCalledTimes(1)
    void t.saver.flush()
    expect(t.save).toHaveBeenCalledTimes(2)
  })

  it('401이면 멈추고 onUnauthorized', async () => {
    const t = setup()
    t.saver.change('a')
    await vi.advanceTimersByTimeAsync(3000)
    t.calls[0].reject(new ApiError(401, { detail: '다시 로그인해 주세요', code: 'UNAUTHORIZED' }))
    await flushPromises()
    expect(t.onUnauthorized).toHaveBeenCalledTimes(1)
    t.saver.change('b')
    await vi.advanceTimersByTimeAsync(10_000)
    expect(t.save).toHaveBeenCalledTimes(1)
  })
})

describe('AutoSaver: 정리', () => {
  it('flush는 기다리지 않고 바로 저장한다', () => {
    const t = setup()
    t.saver.change('a')
    void t.saver.flush()
    expect(t.save).toHaveBeenCalledWith('a')
  })

  it('dispose 후에는 타이머가 돌지 않는다', async () => {
    const t = setup()
    t.saver.change('a')
    t.saver.dispose()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(t.save).not.toHaveBeenCalled()
  })

  it('close: 남은 변경을 한 번 보내고 정리한다', async () => {
    const t = setup()
    t.saver.change('a')
    t.saver.close()
    expect(t.save).toHaveBeenCalledWith('a')
    await vi.advanceTimersByTimeAsync(10_000)
    expect(t.save).toHaveBeenCalledTimes(1)
  })

  it('close: 저장 중이면 끝난 뒤 최신 코드를 보낸다', async () => {
    const t = setup()
    t.saver.change('v1')
    await vi.advanceTimersByTimeAsync(3000)
    t.saver.change('v2')
    t.saver.close()
    expect(t.save).toHaveBeenCalledTimes(1)
    t.calls[0].resolve('2026-11-21T00:00:01Z')
    await flushPromises()
    expect(t.save).toHaveBeenCalledTimes(2)
    expect(t.save).toHaveBeenLastCalledWith('v2')
  })

  it('close: 바뀐 게 없으면 보내지 않는다', () => {
    const t = setup()
    t.saver.close()
    expect(t.save).not.toHaveBeenCalled()
  })
})

describe('saveStatusText', () => {
  const at = new Date('2026-11-21T00:00:00Z')
  const state = (over: Partial<SaveState>): SaveState => ({ status: 'saved', savedAt: at, dirty: false, error: null, ...over })

  it('저장 시각 기준 "3초 전 저장됨"', () => {
    expect(saveStatusText(state({}), new Date('2026-11-21T00:00:03Z'))).toBe('3초 전 저장됨')
    expect(saveStatusText(state({}), new Date('2026-11-21T00:00:00.400Z'))).toBe('방금 저장됨')
    expect(saveStatusText(state({}), new Date('2026-11-21T00:02:05Z'))).toBe('2분 전 저장됨')
    expect(saveStatusText(state({}), new Date('2026-11-21T03:00:00Z'))).toBe('3시간 전 저장됨')
  })

  it('상태별 문구', () => {
    expect(saveStatusText(state({ savedAt: null }))).toBe('아직 저장한 코드 없음')
    expect(saveStatusText(state({ status: 'pending' }))).toBe('저장 대기 중…')
    expect(saveStatusText(state({ status: 'saving' }))).toBe('저장 중…')
    expect(saveStatusText(state({ status: 'retrying' }))).toBe('저장 안 됨 · 다시 시도 중')
    expect(saveStatusText(state({ status: 'failed', error: '다시 로그인해 주세요' }))).toBe(
      '저장 안 됨 · 다시 로그인해 주세요',
    )
  })
})
