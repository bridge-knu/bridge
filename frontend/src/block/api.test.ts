import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  completeBlock,
  getBlock,
  getRunResult,
  runCode,
  saveCode,
  setAuthToken,
  type BlockDetail,
} from '../api.ts'

// 테스트용 응답. 모양은 실제 mock API(GET /blocks/b-array-1) 응답을 줄인 것이다.
const BLOCK: BlockDetail = {
  id: 'b-array-1',
  conceptId: 'array',
  conceptName: '배열',
  minutes: 30,
  video: { url: 'https://www.youtube.com/watch?v=jNQXAC9IVRw', start: 0, end: 600 },
  practice: { lang: 'c', starter: 'int main(void) {}\n', expected: '15\n' },
  checkQuestions: [
    { id: 'q-array-2', conceptId: 'array', conceptName: '배열', prompt: 'p', code: 'int a[4];', choices: ['1', '4'] },
  ],
  savedCode: null,
  savedAt: null,
  done: false,
}

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn(async () => new Response(JSON.stringify(body), { status }))
  vi.stubGlobal('fetch', fn)
  return fn
}

function call(fn: ReturnType<typeof mockFetch>) {
  const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit]
  return { url, method: init.method, body: init.body ? JSON.parse(init.body as string) : undefined, init }
}

afterEach(() => {
  vi.unstubAllGlobals()
  setAuthToken(null)
})

describe('블록 API', () => {
  it('getBlock: GET /api/blocks/{id}, 토큰 포함', async () => {
    const f = mockFetch(200, BLOCK)
    setAuthToken('tok')
    await expect(getBlock('b-array-1')).resolves.toEqual(BLOCK)
    const c = call(f)
    expect([c.method, c.url]).toEqual(['GET', '/api/blocks/b-array-1'])
    expect((c.init.headers as Record<string, string>).Authorization).toBe('Bearer tok')
  })

  it('확인 문제에는 정답 필드가 없다 (응답 그대로 전달)', async () => {
    mockFetch(200, BLOCK)
    const b = await getBlock('b-array-1')
    expect(Object.keys(b.checkQuestions[0])).not.toContain('answer')
  })

  it('getBlock 404 → ApiError(BLOCK_NOT_FOUND)', async () => {
    mockFetch(404, { detail: '블록을 찾을 수 없어요', code: 'BLOCK_NOT_FOUND' })
    const err = await getBlock('nope').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 404, code: 'BLOCK_NOT_FOUND' })
  })

  it('saveCode: PUT /api/code/{blockId} { code }', async () => {
    const f = mockFetch(200, { blockId: 'b-array-1', updatedAt: '2026-11-20T16:49:39Z' })
    await expect(saveCode('b-array-1', 'x')).resolves.toEqual({ blockId: 'b-array-1', updatedAt: '2026-11-20T16:49:39Z' })
    expect(call(f)).toMatchObject({ method: 'PUT', url: '/api/code/b-array-1', body: { code: 'x' } })
  })

  it('runCode: POST /api/run { lang, code, blockId } → jobId', async () => {
    const f = mockFetch(202, { jobId: 'abc' })
    await expect(runCode({ lang: 'c', code: 'x', blockId: 'b-array-1' })).resolves.toEqual({ jobId: 'abc' })
    expect(call(f)).toMatchObject({ method: 'POST', url: '/api/run', body: { lang: 'c', code: 'x', blockId: 'b-array-1' } })
  })

  it('getRunResult: GET /api/run/{jobId}', async () => {
    const f = mockFetch(200, { jobId: 'abc', status: 'running' })
    await getRunResult('abc')
    expect(call(f)).toMatchObject({ method: 'GET', url: '/api/run/abc' })
  })

  it('completeBlock: POST /api/blocks/{id}/complete { checkAnswers }', async () => {
    const res = { blockId: 'b-array-1', done: true, correctCount: 1, totalCount: 1, nextBlockId: 'b-pointer-1' }
    const f = mockFetch(200, res)
    await expect(
      completeBlock('b-array-1', { checkAnswers: [{ questionId: 'q-array-2', choice: 1 }] }),
    ).resolves.toEqual(res)
    expect(call(f)).toMatchObject({
      method: 'POST',
      url: '/api/blocks/b-array-1/complete',
      body: { checkAnswers: [{ questionId: 'q-array-2', choice: 1 }] },
    })
  })
})
