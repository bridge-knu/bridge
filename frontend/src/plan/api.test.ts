import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, generatePlan, getPlan, setAuthToken, type Plan } from '../api.ts'

// 테스트용 응답. 모양은 backend/app/api/schemas.py의 Plan(mock API 응답)을 따른다.
const PLAN: Plan = {
  returnDate: '2027-03-02',
  dailyMinutes: 60,
  todayRemainingMinutes: 60,
  days: [
    {
      date: '2026-11-21',
      blocks: [{ order: 1, blockId: 'b-array-1', conceptId: 'array', conceptName: '배열', minutes: 30, done: false }],
    },
  ],
}

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn(async () => new Response(JSON.stringify(body), { status }))
  vi.stubGlobal('fetch', fn)
  return fn
}

afterEach(() => {
  vi.unstubAllGlobals()
  setAuthToken(null)
})

describe('플랜 API', () => {
  it('getPlan: GET /api/plan, 토큰을 붙이고 응답을 그대로 돌려준다', async () => {
    const fetch = mockFetch(200, PLAN)
    setAuthToken('tok')
    await expect(getPlan()).resolves.toEqual(PLAN)
    expect(fetch).toHaveBeenCalledTimes(1)
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/plan')
    expect(init.method).toBe('GET')
    expect(init.body).toBeUndefined()
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok')
  })

  it('generatePlan: POST /api/plan/generate, 요청 본문 없음', async () => {
    const fetch = mockFetch(200, PLAN)
    await expect(generatePlan()).resolves.toEqual(PLAN)
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/plan/generate')
    expect(init.method).toBe('POST')
    expect(init.body).toBeUndefined()
  })

  it('실패하면 ApiError(status, detail, code)', async () => {
    mockFetch(401, { detail: '다시 로그인해 주세요', code: 'UNAUTHORIZED' })
    const err = await getPlan().catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 401, detail: '다시 로그인해 주세요', code: 'UNAUTHORIZED' })
  })
})
