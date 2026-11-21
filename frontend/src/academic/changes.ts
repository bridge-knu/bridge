// 학사 변경 안내 (C7). content/academic_changes.json을 읽어 입학년도·휴학·복학 시기에 맞는 항목만 고른다.
// 백엔드 API 없이 프론트에서만 처리한다. JSON은 빌드할 때 번들에 들어간다.
//
// content/academic_changes.json 항목 형식 (배열)
// {
//   "id": "고유 id (문자열)",
//   "effectiveDate": "시행일 YYYY-MM-DD (학기 시작부터면 1학기 YYYY-03-01, 2학기 YYYY-09-01)",
//   "admissionYearFrom": 적용 대상 첫 입학년도 (숫자) 또는 null (처음부터 모두),
//   "admissionYearTo": 적용 대상 마지막 입학년도 (숫자) 또는 null (이후 모두),
//   "title": "변경 제목",
//   "summary": "변경 내용 요약",
//   "sourceUrl": "공식 공지 주소 (https)"
// }
// 시행 시기(effectiveDate)는 "언제부터 바뀌었나", 적용 대상(admissionYearFrom~To)은 "누구에게 해당하나"다.
// 내용은 반드시 경북대·학부 공식 공지로 확인한 것만 넣는다 (개발 가이드: AI가 학사 변경 내용을 만들면 안 됨).

export interface AcademicChange {
  id: string
  /** 시행일 YYYY-MM-DD */
  effectiveDate: string
  /** 적용 대상 첫 입학년도. null이면 아래로 제한 없음 */
  admissionYearFrom: number | null
  /** 적용 대상 마지막 입학년도. null이면 위로 제한 없음 */
  admissionYearTo: number | null
  title: string
  summary: string
  /** 공식 출처 (https) */
  sourceUrl: string
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

function isValidDate(value: unknown): value is string {
  if (typeof value !== 'string' || !DATE_RE.test(value)) return false
  const [y, m, d] = value.split('-').map(Number)
  const date = new Date(Date.UTC(y, m - 1, d))
  return date.getUTCFullYear() === y && date.getUTCMonth() === m - 1 && date.getUTCDate() === d
}

function isYearOrNull(value: unknown): value is number | null {
  return value === null || (typeof value === 'number' && Number.isInteger(value) && value >= 1900 && value <= 2100)
}

function isText(value: unknown): value is string {
  return typeof value === 'string' && value.trim() !== ''
}

/** 공식 출처는 https 주소만 받는다 (javascript: 같은 주소가 링크로 들어가지 않게) */
export function isSafeSourceUrl(value: unknown): value is string {
  if (typeof value !== 'string') return false
  try {
    return new URL(value).protocol === 'https:'
  } catch {
    return false
  }
}

/**
 * JSON을 검사해서 형식에 맞는 항목만 돌려준다. 틀린 항목은 화면에 내지 않고 invalid에 id(또는 위치)를 모은다.
 * 출처가 없거나 https가 아닌 항목도 뺀다 (출처 링크 필수).
 */
export function parseChanges(raw: unknown): { changes: AcademicChange[]; invalid: string[] } {
  const changes: AcademicChange[] = []
  const invalid: string[] = []
  if (!Array.isArray(raw)) return { changes, invalid: ['(배열이 아님)'] }

  const seen = new Set<string>()
  raw.forEach((item: unknown, index) => {
    const label = typeof item === 'object' && item !== null && 'id' in item ? String(item.id) : `#${index}`
    if (typeof item !== 'object' || item === null) {
      invalid.push(label)
      return
    }
    const c = item as Record<string, unknown>
    const ok =
      isText(c.id) &&
      !seen.has(c.id) &&
      isValidDate(c.effectiveDate) &&
      isYearOrNull(c.admissionYearFrom) &&
      isYearOrNull(c.admissionYearTo) &&
      (c.admissionYearFrom === null || c.admissionYearTo === null || c.admissionYearFrom <= c.admissionYearTo) &&
      isText(c.title) &&
      isText(c.summary) &&
      isSafeSourceUrl(c.sourceUrl)
    if (!ok) {
      invalid.push(label)
      return
    }
    seen.add(c.id as string)
    changes.push({
      id: c.id as string,
      effectiveDate: c.effectiveDate as string,
      admissionYearFrom: c.admissionYearFrom as number | null,
      admissionYearTo: c.admissionYearTo as number | null,
      title: c.title as string,
      summary: c.summary as string,
      sourceUrl: c.sourceUrl as string,
    })
  })
  return { changes, invalid }
}

// ---- 입력 ----

export type Term = 1 | 2

export interface Semester {
  year: number
  term: Term
}

export interface AcademicQuery {
  admissionYear: number
  leaveStart: Semester
  returnAt: Semester
}

/** 화면 입력값 (select·input의 문자열 그대로) */
export interface AcademicInput {
  admissionYear: string
  leaveYear: string
  leaveTerm: string
  returnYear: string
  returnTerm: string
}

export const ADMISSION_YEAR_MIN = 2000

/** 학기 시작일. 1학기 3월 1일, 2학기 9월 1일 */
export function semesterStart(s: Semester): string {
  return `${s.year}-${s.term === 1 ? '03' : '09'}-01`
}

function toYear(value: string): number | null {
  if (!/^\d{4}$/.test(value.trim())) return null
  return Number(value)
}

function toTerm(value: string): Term | null {
  return value === '1' ? 1 : value === '2' ? 2 : null
}

function semesterIndex(s: Semester): number {
  return s.year * 2 + (s.term - 1)
}

/**
 * 입력을 검사한다. 문제가 없으면 AcademicQuery, 있으면 안내 문구.
 * thisYear: 오늘 연도 (입학년도는 올해까지만)
 */
export function validateInput(input: AcademicInput, thisYear: number): AcademicQuery | string {
  const admissionYear = toYear(input.admissionYear)
  if (admissionYear === null || admissionYear < ADMISSION_YEAR_MIN || admissionYear > thisYear) {
    return `입학년도를 ${ADMISSION_YEAR_MIN}~${thisYear}년 중에서 선택해 주세요`
  }
  const leaveYear = toYear(input.leaveYear)
  const leaveTerm = toTerm(input.leaveTerm)
  if (leaveYear === null || leaveTerm === null) {
    return '휴학 시작 시기를 연도와 학기까지 선택해 주세요'
  }
  const returnYear = toYear(input.returnYear)
  const returnTerm = toTerm(input.returnTerm)
  if (returnYear === null || returnTerm === null) {
    return '복학 시기를 연도와 학기까지 선택해 주세요'
  }
  const leaveStart: Semester = { year: leaveYear, term: leaveTerm }
  const returnAt: Semester = { year: returnYear, term: returnTerm }
  if (leaveYear < admissionYear) {
    return '휴학 시작 시기는 입학년도 이후로 선택해 주세요'
  }
  if (semesterIndex(returnAt) <= semesterIndex(leaveStart)) {
    return '복학 시기는 휴학 시작 시기보다 뒤 학기로 선택해 주세요'
  }
  return { admissionYear, leaveStart, returnAt }
}

// ---- 필터 ----

/** 이 입학년도가 적용 대상인가 */
export function appliesToAdmissionYear(change: AcademicChange, admissionYear: number): boolean {
  if (change.admissionYearFrom !== null && admissionYear < change.admissionYearFrom) return false
  if (change.admissionYearTo !== null && admissionYear > change.admissionYearTo) return false
  return true
}

/** 특정 입학년도만 대상인 항목인가 (전체 학생 대상이 아님) */
export function isAdmissionSpecific(change: AcademicChange): boolean {
  return change.admissionYearFrom !== null || change.admissionYearTo !== null
}

/**
 * 휴학 시작 학기 시작일 ~ 복학 학기 시작일(둘 다 포함) 사이에 시행됐고, 내 입학년도가 대상인 항목.
 * 휴학을 시작한 학기에 시행된 변경은 겪지 못했으니 넣고, 복학 학기부터 시행되는 변경도 복학하면 바로 적용되니 넣는다.
 * 시행일 오름차순 (같은 날이면 id순).
 */
export function filterChanges(changes: AcademicChange[], query: AcademicQuery): AcademicChange[] {
  const from = semesterStart(query.leaveStart)
  const to = semesterStart(query.returnAt)
  return changes
    .filter((c) => c.effectiveDate >= from && c.effectiveDate <= to)
    .filter((c) => appliesToAdmissionYear(c, query.admissionYear))
    .sort((a, b) => a.effectiveDate.localeCompare(b.effectiveDate) || a.id.localeCompare(b.id))
}

/** 타임라인용 연도별 묶음 (입력 순서 유지) */
export function groupByYear(changes: AcademicChange[]): { year: number; changes: AcademicChange[] }[] {
  const groups: { year: number; changes: AcademicChange[] }[] = []
  for (const c of changes) {
    const year = Number(c.effectiveDate.slice(0, 4))
    const last = groups[groups.length - 1]
    if (last && last.year === year) last.changes.push(c)
    else groups.push({ year, changes: [c] })
  }
  return groups
}

// ---- 표시 ----

/** "2025년 3월 1일" */
export function formatEffectiveDate(date: string): string {
  const [y, m, d] = date.split('-').map(Number)
  return `${y}년 ${m}월 ${d}일`
}

/** "2023학번부터", "2019학번까지", "2020~2022학번", "2021학번", "전체 학번" */
export function admissionTargetText(change: AcademicChange): string {
  const { admissionYearFrom: from, admissionYearTo: to } = change
  if (from === null && to === null) return '전체 학번'
  if (from !== null && to === null) return `${from}학번부터`
  if (from === null && to !== null) return `${to}학번까지`
  if (from === to) return `${from}학번`
  return `${from}~${to}학번`
}

/** "2024년 1학기" */
export function semesterText(s: Semester): string {
  return `${s.year}년 ${s.term}학기`
}
