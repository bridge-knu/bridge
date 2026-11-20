import { describe, expect, it } from 'vitest'
import { ApiError, type Plan, type PlanBlock } from '../api.ts'
import {
  classifyPlanError,
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

  it('오늘 블록을 다 끝냈거나 남은 시간이 0이면 todayDone', () => {
    expect(toPlanView(plan({ todayRemainingMinutes: 0 }), TODAY).today).toEqual({ kind: 'todayDone' })
    const done = plan({ days: [{ date: TODAY, blocks: [block('b-a', 1, true)] }], todayRemainingMinutes: 30 })
    expect(toPlanView(done, TODAY).today).toEqual({ kind: 'todayDone' })
    expect(todayGuideText({ kind: 'todayDone' })).toBe('오늘 블록을 모두 끝냈어요')
  })

  it('오늘 날짜가 플랜에 없으면 noToday', () => {
    const v = toPlanView(plan(), '2026-12-25')
    expect(v.today).toEqual({ kind: 'noToday' })
    expect(v.reachableToday.size).toBe(0)
    expect(todayGuideText(v.today)).toBe('오늘은 배정된 블록이 없어요')
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

describe('날짜', () => {
  it('localToday는 로컬 날짜 YYYY-MM-DD', () => {
    expect(localToday(new Date(2026, 0, 5, 23, 59))).toBe('2026-01-05')
  })

  it('formatDate는 "11월 21일 (토)"', () => {
    expect(formatDate('2026-11-21')).toBe('11월 21일 (토)')
    expect(formatDate('2027-03-02')).toBe('3월 2일 (화)')
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
