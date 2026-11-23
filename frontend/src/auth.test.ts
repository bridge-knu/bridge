import { afterEach, describe, expect, it, vi } from 'vitest'

// 브라우저의 sessionStorage 대신 쓰는 메모리 저장소
function fakeStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial))
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
    data,
  }
}

// api.ts는 불러올 때 저장된 토큰을 읽으므로, 새로고침을 흉내 내려면 모듈을 다시 불러온다
async function loadApi() {
  vi.resetModules()
  return import('./api.ts')
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('로그인 토큰 저장 (새로고침해도 유지)', () => {
  it('저장한 토큰은 새로고침 후에도 남아 있다', async () => {
    const storage = fakeStorage()
    vi.stubGlobal('sessionStorage', storage)
    const api = await loadApi()
    api.setAuthToken('tok')
    expect(storage.data.get('bridge.token')).toBe('tok')

    const reloaded = await loadApi()
    expect(reloaded.getAuthToken()).toBe('tok')
  })

  it('로그아웃(null)하면 저장소에서도 지운다', async () => {
    const storage = fakeStorage({ 'bridge.token': 'tok' })
    vi.stubGlobal('sessionStorage', storage)
    const api = await loadApi()
    expect(api.getAuthToken()).toBe('tok')
    api.setAuthToken(null)
    expect(storage.data.has('bridge.token')).toBe(false)
    expect((await loadApi()).getAuthToken()).toBeNull()
  })

  it('저장소를 쓸 수 없어도 메모리 토큰으로 동작한다', async () => {
    vi.stubGlobal('sessionStorage', {
      getItem: () => {
        throw new Error('blocked')
      },
      setItem: () => {
        throw new Error('blocked')
      },
      removeItem: () => {
        throw new Error('blocked')
      },
    })
    const api = await loadApi()
    expect(api.getAuthToken()).toBeNull()
    api.setAuthToken('tok')
    expect(api.getAuthToken()).toBe('tok')
  })

  it('로그인·로그아웃을 구독한 화면에 알린다', async () => {
    vi.stubGlobal('sessionStorage', fakeStorage())
    const api = await loadApi()
    const listener = vi.fn()
    const unsubscribe = api.subscribeAuthToken(listener)
    api.setAuthToken('tok')
    api.setAuthToken(null)
    expect(listener).toHaveBeenCalledTimes(2)
    unsubscribe()
    api.setAuthToken('again')
    expect(listener).toHaveBeenCalledTimes(2)
  })
})

describe('체험 계정 (POST /auth/demo)', () => {
  it('본문 없이 POST /api/auth/demo를 부르고 토큰을 돌려준다', async () => {
    vi.stubGlobal('sessionStorage', fakeStorage())
    const fetchFn = vi.fn(async () => new Response(JSON.stringify({ token: 'trial', isNewUser: false }), { status: 200 }))
    vi.stubGlobal('fetch', fetchFn)
    const api = await loadApi()
    const res = await api.startTrial()
    expect(res).toEqual({ token: 'trial', isNewUser: false })
    const [url, init] = fetchFn.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/auth/demo')
    expect(init.method).toBe('POST')
    expect(init.body).toBeUndefined()
  })

  it('너무 많이 만들면 서버 안내 문구가 담긴 ApiError', async () => {
    vi.stubGlobal('sessionStorage', fakeStorage())
    const body = { detail: '요청이 너무 많아요. 잠시 후 다시 시도해 주세요', code: 'TOO_MANY_REQUESTS' }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status: 429 })))
    const api = await loadApi()
    await expect(api.startTrial()).rejects.toMatchObject({ status: 429, detail: body.detail })
  })
})
