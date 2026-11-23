import { describe, expect, it } from 'vitest'
import { ApiError, type Plan, type PlanBlock } from '../api.ts'
import {
  classifyPlanError,
  dDayLabel,
  daysUntil,
  formatDate,
  localToday,
  planErrorMessage,
  todayGuideText,
  toPlanView,
} from './view.ts'

// 테스트용 데이터. 모양은 backend/app/api/schemas.py의 Plan(mock API 응답)을 따른다.
const block = (blockId: string, order: number, done = false, minutes = 30): PlanBlock => ({
  order,
  blockId,
  conceptId: blockId.replace(/^b-|-\d+$/g, ''),
  conceptName: blockId,
  minutes,
  done,
})

const TODAY = '2026-11-21'

const plan = (over: Partial<Plan> = {}): Plan => ({
  today: TODAY,
  returnDate: '2027-03-02',
  dailyMinutes: 60,
  todayRemainingMinutes: 60,
  days: [
    { date: '2026-11-22', blocks: [block('b-linked_list-1', 1)] },
    { date: TODAY, blocks: [block('b-pointer-1', 2), block('b-array-1', 1)] },
  ],
  ...over,
})

describe('toPlanView: 날짜별 그룹', () => {
  it('오늘을 맨 앞에 두고 나머지는 날짜순, 블록은 order순', () => {
    const v = toPlanView(plan(), TODAY)
    expect(v.days.map((d) => d.date)).toEqual([TODAY, '2026-11-22'])
    expect(v.days[0].isToday).toBe(true)
    expect(v.days[1].isToday).toBe(false)
    expect(v.days[0].blocks.map((b) => b.blockId)).toEqual(['b-array-1', 'b-pointer-1'])
    expect(v.days[0].minutes).toBe(60)
  })

  it('지난 날짜는 오늘 뒤에 날짜순으로 남긴다', () => {
    const v = toPlanView(
      plan({
        days: [
          { date: '2026-11-22', blocks: [block('b-c', 1)] },
          { date: TODAY, blocks: [block('b-b', 1)] },
          { date: '2026-11-20', blocks: [block('b-a', 1)] },
        ],
      }),
      TODAY,
    )
    expect(v.days.map((d) => d.date)).toEqual([TODAY, '2026-11-20', '2026-11-22'])
    expect(v.days.map((d) => d.isPast)).toEqual([false, true, false])
  })

  it('블록이 없는 날은 뺀다', () => {
    const v = toPlanView(plan({ days: [{ date: TODAY, blocks: [] }] }), TODAY)
    expect(v.days).toEqual([])
    expect(v.totalBlocks).toBe(0)
  })

  it('완료 수와 날짜별 완료', () => {
    const v = toPlanView(
      plan({
        days: [
          { date: TODAY, blocks: [block('b-a', 1, true), block('b-b', 2, true)] },
          { date: '2026-11-22', blocks: [block('b-c', 1)] },
        ],
        todayRemainingMinutes: 0,
      }),
      TODAY,
    )
    expect(v.days[0].allDone).toBe(true)
    expect(v.doneBlocks).toBe(2)
    expect(v.totalBlocks).toBe(3)
    expect(v.allDone).toBe(false)
  })

  it('모든 블록을 끝내면 allDone', () => {
    const v = toPlanView(
      plan({ days: [{ date: TODAY, blocks: [block('b-a', 1, true)] }], todayRemainingMinutes: 0 }),
      TODAY,
    )
    expect(v.allDone).toBe(true)
  })
})

describe('toPlanView: 오늘 남은 시간', () => {
  it('남은 시간 안에 들어가는 마지막 블록까지 가능', () => {
    const v = toPlanView(plan({ todayRemainingMinutes: 60 }), TODAY)
    expect(v.today).toEqual({
      kind: 'remaining',
      minutes: 60,
      lastBlockId: 'b-pointer-1',
      lastConceptName: 'b-pointer-1',
      todayBlocksDone: false,
    })
    expect([...v.reachableToday]).toEqual(['b-array-1', 'b-pointer-1'])
  })

  it('가이드 예시: 남은 40분이면 30분 블록 1개까지', () => {
    const v = toPlanView(plan({ todayRemainingMinutes: 40 }), TODAY)
    expect(v.today).toMatchObject({ kind: 'remaining', minutes: 40, lastBlockId: 'b-array-1' })
    expect(todayGuideText(v.today)).toBe('오늘 남은 시간 40분, b-array-1 블록까지 가능해요')
  })

  it('끝낸 블록은 건너뛰고 남은 블록부터 센다', () => {
    const v = toPlanView(
      plan({
        days: [{ date: TODAY, blocks: [block('b-a', 1, true), block('b-b', 2), block('b-c', 3)] }],
        todayRemainingMinutes: 30,
      }),
      TODAY,
    )
    expect(v.today).toMatchObject({ lastBlockId: 'b-b' })
    expect([...v.reachableToday]).toEqual(['b-b'])
  })

  it('남은 시간이 블록 하나보다 짧으면 가능한 블록 없음', () => {
    const v = toPlanView(plan({ todayRemainingMinutes: 20 }), TODAY)
    expect(v.today).toMatchObject({ kind: 'remaining', minutes: 20, lastBlockId: null })
    expect(todayGuideText(v.today)).toContain('시간이 부족해요')
  })

  it('남은 시간이 0이면 timeUsed (오늘 블록이 남아 있어도)', () => {
    const v = toPlanView(plan({ todayRemainingMinutes: 0 }))
    expect(v.today).toEqual({ kind: 'timeUsed' })
    expect(v.reachableToday.size).toBe(0)
    expect(todayGuideText(v.today)).toBe('오늘 공부할 시간을 모두 썼어요. 내일 이어서 해요')
  })

  it('오늘 블록을 다 끝냈어도 남은 시간이 있으면 다음 날 블록까지 이어서 센다', () => {
    const v = toPlanView(
      plan({
        days: [
          { date: TODAY, blocks: [block('b-a', 1, true)] },
          { date: '2026-11-22', blocks: [block('b-b', 1), block('b-c', 2)] },
        ],
        todayRemainingMinutes: 30,
      }),
    )
    expect(v.today).toEqual({
      kind: 'remaining',
      minutes: 30,
      lastBlockId: 'b-b',
      lastConceptName: 'b-b',
      todayBlocksDone: true,
    })
    expect([...v.reachableToday]).toEqual(['b-b'])
    expect(todayGuideText(v.today)).toBe('오늘 블록을 모두 끝냈어요. 오늘 남은 시간 30분, b-b 블록까지 가능해요')
  })

  it('지난 날 끝내지 못한 블록부터 날짜순으로 더한다', () => {
    const v = toPlanView(
      plan({
        days: [
          { date: TODAY, blocks: [block('b-today', 1)] },
          { date: '2026-11-20', blocks: [block('b-past', 1)] },
        ],
        todayRemainingMinutes: 30,
      }),
    )
    expect([...v.reachableToday]).toEqual(['b-past'])
    expect(v.today).toMatchObject({ kind: 'remaining', lastBlockId: 'b-past', todayBlocksDone: false })
  })

  it('오늘 날짜가 플랜에 없어도 남은 시간 안의 블록을 보여 준다', () => {
    const v = toPlanView(plan({ today: '2026-11-20' }))
    expect(v.days.some((d) => d.isToday)).toBe(false)
    expect(v.today).toMatchObject({ kind: 'remaining', lastBlockId: 'b-pointer-1', todayBlocksDone: true })
  })
})

describe('toPlanView: 오늘 날짜', () => {
  it('브라우저 날짜가 아니라 API의 today로 오늘을 정한다', () => {
    // 브라우저는 UTC 등 다른 날짜여도 서버(KST)의 today를 따른다
    const v = toPlanView(plan({ today: '2026-11-22' }))
    expect(v.todayDate).toBe('2026-11-22')
    expect(v.days[0]).toMatchObject({ date: '2026-11-22', isToday: true })
    expect(v.days.find((d) => d.date === TODAY)).toMatchObject({ isToday: false, isPast: true })
  })

  it('응답에 today가 없을 때만 브라우저 날짜를 쓴다 (PR #38 병합 전)', () => {
    const { today: _omit, ...legacy } = plan()
    void _omit
    expect(toPlanView(legacy).todayDate).toBe(localToday())
  })
})

describe('toPlanView: 미룬 개념', () => {
  it('API에 필드가 없으면 null (표시하지 않음)', () => {
    const v = toPlanView(plan(), TODAY)
    expect(v.deferred).toBeNull()
    expect(v.message).toBeNull()
  })

  it('빈 배열이면 미룬 개념 없음', () => {
    const v = toPlanView(plan({ deferredConcepts: [], message: null }), TODAY)
    expect(v.deferred).toEqual([])
  })

  it('미룬 개념과 안내 문구를 그대로 넘긴다', () => {
    const deferredConcepts = [{ conceptId: 'graph', conceptName: '그래프', blocks: 2 }]
    const message = '시간이 부족해 그래프은(는) 복학 후로 미뤘어요'
    const v = toPlanView(plan({ deferredConcepts, message }), TODAY)
    expect(v.deferred).toEqual(deferredConcepts)
    expect(v.message).toBe(message)
    // 미룬 개념은 날짜별 블록에 섞이지 않는다
    expect(v.days.flatMap((d) => d.blocks).some((b) => b.conceptId === 'graph')).toBe(false)
  })
})

describe('toPlanView: 같은 개념 블록 번호', () => {
  const b = (blockId: string, conceptId: string, order: number): PlanBlock => ({
    order,
    blockId,
    conceptId,
    conceptName: conceptId,
    minutes: 30,
    done: false,
  })

  it('여러 블록으로 나뉜 개념만 날짜·순서대로 1/N을 붙인다', () => {
    const view = toPlanView(
      plan({
        today: '2026-11-23',
        days: [
          // 일부러 날짜를 뒤섞어 둔다 (번호는 날짜순)
          { date: '2026-11-24', blocks: [b('p2', 'pointer', 1), b('s1', 'stack', 2)] },
          { date: '2026-11-23', blocks: [b('r1', 'recursion', 1), b('p1', 'pointer', 2)] },
        ],
      }),
    )
    expect(view.parts.get('p1')).toEqual({ index: 1, total: 2 })
    expect(view.parts.get('p2')).toEqual({ index: 2, total: 2 })
    expect(view.parts.has('r1')).toBe(false)
    expect(view.parts.has('s1')).toBe(false)
  })

  it('lastDate는 블록이 있는 마지막 날짜', () => {
    const view = toPlanView(
      plan({
        today: '2026-11-23',
        days: [
          { date: '2026-11-25', blocks: [] },
          { date: '2026-11-24', blocks: [b('a', 'a', 1)] },
        ],
      }),
    )
    expect(view.lastDate).toBe('2026-11-24')
    expect(toPlanView(plan({ days: [] })).lastDate).toBeNull()
  })
})

describe('날짜', () => {
  it('localToday는 로컬 날짜 YYYY-MM-DD', () => {
    expect(localToday(new Date(2026, 0, 5, 23, 59))).toBe('2026-01-05')
  })

  it('formatDate는 "11월 21일 (토)"', () => {
    expect(formatDate('2026-11-21')).toBe('11월 21일 (토)')
    expect(formatDate('2027-03-02')).toBe('3월 2일 (화)')
  })

  it('daysUntil은 두 날짜 사이 날 수 (월·연도 넘김, 서머타임 영향 없음)', () => {
    expect(daysUntil('2026-11-23', '2026-11-23')).toBe(0)
    expect(daysUntil('2026-11-23', '2027-03-02')).toBe(99)
    expect(daysUntil('2027-02-28', '2027-03-01')).toBe(1)
    expect(daysUntil('2027-03-05', '2027-03-02')).toBe(-3)
  })

  it('dDayLabel은 D-N, 당일 D-Day, 지나면 D+N', () => {
    expect(dDayLabel(42)).toBe('D-42')
    expect(dDayLabel(0)).toBe('D-Day')
    expect(dDayLabel(-3)).toBe('D+3')
  })
})

describe('오류', () => {
  it('401·UNAUTHORIZED는 unauthorized, 나머지는 other', () => {
    expect(classifyPlanError(new ApiError(401, { detail: 'x', code: 'UNAUTHORIZED' }))).toBe('unauthorized')
    expect(classifyPlanError(new ApiError(401, { detail: 'x' }))).toBe('unauthorized')
    expect(classifyPlanError(new ApiError(503, { detail: 'x', code: 'SERVICE_UNAVAILABLE' }))).toBe('other')
    expect(classifyPlanError(new TypeError('Failed to fetch'))).toBe('other')
  })

  it('안내 문구', () => {
    expect(planErrorMessage(new ApiError(503, { detail: '잠시 후 다시 시도해 주세요' }))).toBe(
      '잠시 후 다시 시도해 주세요',
    )
    expect(planErrorMessage(new ApiError(500, 'Internal Server Error'))).toBe('잠시 후 다시 시도해 주세요')
    expect(planErrorMessage(new TypeError('Failed to fetch'))).toContain('서버에 연결할 수 없어요')
    expect(planErrorMessage(new Error('x'))).toContain('플랜을 불러오지 못했어요')
  })
})
