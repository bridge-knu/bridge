// GET /plan, POST /plan/generate 응답(api.ts의 Plan)을 화면용 형태로 바꾼다.
// 블록 배치와 남은 시간 계산은 백엔드(플랜 엔진)가 하고, 여기서는 받은 값을 나누고 꾸미기만 한다.
// 아래 타입은 화면 내부용이며 API 규격이 아니다. API 규격은 api.ts에 있다.

import { ApiError, type DeferredConcept, type Plan, type PlanBlock } from '../api.ts'

export interface PlanDayView {
  /** YYYY-MM-DD */
  date: string
  isToday: boolean
  /** 오늘보다 앞선 날짜 (끝내지 못한 블록이 남아 있을 수 있음) */
  isPast: boolean
  blocks: PlanBlock[]
  minutes: number
  allDone: boolean
}

/** 오늘 남은 시간 안내 */
export type TodayGuide =
  /**
   * 오늘 공부할 시간이 남았다. lastBlockId: 남은 시간 안에 끝낼 수 있는 마지막 블록 (없으면 null).
   * todayBlocksDone: 오늘 날짜에 배정된 블록은 이미 다 끝냈다 (배정된 블록이 없을 때도 true)
   */
  | {
      kind: 'remaining'
      minutes: number
      lastBlockId: string | null
      lastConceptName: string | null
      todayBlocksDone: boolean
    }
  /** 오늘 가용 시간을 다 썼다 (todayRemainingMinutes가 0) */
  | { kind: 'timeUsed' }

export interface PlanView {
  /** 오늘 날짜 (API의 today, YYYY-MM-DD) */
  todayDate: string
  returnDate: string
  dailyMinutes: number
  /** 오늘이 맨 앞, 나머지는 날짜순 */
  days: PlanDayView[]
  today: TodayGuide
  /** 오늘 남은 시간 안에 할 수 있는 블록 id */
  reachableToday: Set<string>
  totalBlocks: number
  doneBlocks: number
  allDone: boolean
  /** 미룬 개념. API에 필드가 없으면 null (정보 없음), 있으면 배열 (비어 있을 수 있음) */
  deferred: DeferredConcept[] | null
  /** 미룬 개념 안내 문구 (백엔드가 줄 때만) */
  message: string | null
}

/** 브라우저 기준 오늘 날짜 (YYYY-MM-DD, 로컬 시간). API가 today를 주지 않을 때만 대신 쓴다 */
export function localToday(now: Date = new Date()): string {
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/**
 * 끝내지 않은 블록을 플랜 순서(날짜 → order)대로 더해 todayRemainingMinutes 안에 들어가는 블록까지 고른다.
 * (README "플랜의 날짜와 남은 시간": 안 끝낸 블록 시간을 순서대로 더해서 이 값 안에 드는 데까지)
 * 남은 시간 자체는 백엔드 값을 그대로 쓴다.
 */
function reachable(blocks: PlanBlock[], remainingMinutes: number): PlanBlock[] {
  const result: PlanBlock[] = []
  let used = 0
  for (const b of blocks) {
    if (b.done) continue
    if (used + b.minutes > remainingMinutes) break
    used += b.minutes
    result.push(b)
  }
  return result
}

/**
 * today: 오늘 날짜. 기본값은 API의 plan.today (한국 시간)이고, 응답에 없을 때만 브라우저 날짜를 쓴다.
 */
export function toPlanView(plan: Plan, today: string = plan.today ?? localToday()): PlanView {
  const sorted = [...plan.days]
    .sort((a, b) => a.date.localeCompare(b.date))
    .map<PlanDayView>((d) => {
      const blocks = [...d.blocks].sort((a, b) => a.order - b.order)
      return {
        date: d.date,
        isToday: d.date === today,
        isPast: d.date < today,
        blocks,
        minutes: blocks.reduce((sum, b) => sum + b.minutes, 0),
        allDone: blocks.length > 0 && blocks.every((b) => b.done),
      }
    })
    .filter((d) => d.blocks.length > 0)

  // 오늘을 맨 앞으로. 지난 날짜(끝내지 못한 블록)는 오늘 뒤에 날짜순으로 남긴다.
  const todayDay = sorted.find((d) => d.isToday)
  const days = todayDay ? [todayDay, ...sorted.filter((d) => d !== todayDay)] : sorted

  const all = sorted.flatMap((d) => d.blocks)

  let guide: TodayGuide
  let reachableToday = new Set<string>()
  if (plan.todayRemainingMinutes <= 0) {
    guide = { kind: 'timeUsed' }
  } else {
    const fit = reachable(all, plan.todayRemainingMinutes)
    reachableToday = new Set(fit.map((b) => b.blockId))
    const last = fit.length > 0 ? fit[fit.length - 1] : null
    guide = {
      kind: 'remaining',
      minutes: plan.todayRemainingMinutes,
      lastBlockId: last?.blockId ?? null,
      lastConceptName: last?.conceptName ?? null,
      todayBlocksDone: !todayDay || todayDay.allDone,
    }
  }

  const doneBlocks = all.filter((b) => b.done).length

  return {
    todayDate: today,
    returnDate: plan.returnDate,
    dailyMinutes: plan.dailyMinutes,
    days,
    today: guide,
    reachableToday,
    totalBlocks: all.length,
    doneBlocks,
    allDone: all.length > 0 && doneBlocks === all.length,
    deferred: plan.deferredConcepts ?? null,
    message: plan.message ?? null,
  }
}

/** 오늘 남은 시간 안내 문구 */
export function todayGuideText(guide: TodayGuide): string {
  switch (guide.kind) {
    case 'remaining': {
      const prefix = guide.todayBlocksDone ? '오늘 블록을 모두 끝냈어요. ' : ''
      return guide.lastConceptName
        ? `${prefix}오늘 남은 시간 ${guide.minutes}분, ${guide.lastConceptName} 블록까지 가능해요`
        : `${prefix}오늘 남은 시간 ${guide.minutes}분, 다음 블록을 끝내기에는 시간이 부족해요`
    }
    case 'timeUsed':
      return '오늘 공부할 시간을 모두 썼어요. 내일 이어서 해요'
  }
}

/** "11월 21일 (토)" */
export function formatDate(date: string): string {
  const [y, m, d] = date.split('-').map(Number)
  const day = new Date(y, m - 1, d)
  const weekday = ['일', '월', '화', '수', '목', '금', '토'][day.getDay()]
  return `${m}월 ${d}일 (${weekday})`
}

/**
 * unauthorized: 토큰 없음·만료 → 로그인 화면
 * other: 그 밖의 오류 (5xx, 네트워크 실패 등) → 안내 + 다시 시도
 */
export type PlanErrorKind = 'unauthorized' | 'other'

export function classifyPlanError(err: unknown): PlanErrorKind {
  if (!(err instanceof ApiError)) return 'other'
  if (err.code === 'UNAUTHORIZED' || err.status === 401) return 'unauthorized'
  return 'other'
}

export function planErrorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.detail ?? '잠시 후 다시 시도해 주세요'
  if (err instanceof TypeError) return '서버에 연결할 수 없어요. 네트워크를 확인해 주세요'
  return '플랜을 불러오지 못했어요. 다시 시도해 주세요'
}
