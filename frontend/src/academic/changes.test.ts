import { describe, expect, it } from 'vitest'
import rawChanges from '../../../content/academic_changes.json'
import {
  admissionTargetText,
  appliesToAdmissionYear,
  filterChanges,
  formatEffectiveDate,
  groupByYear,
  isSafeSourceUrl,
  parseChanges,
  semesterStart,
  validateInput,
  type AcademicChange,
  type AcademicInput,
  type AcademicQuery,
} from './changes.ts'

// 테스트 전용 가짜 항목. 실제 학사 변경 내용이 아니다.
const change = (over: Partial<AcademicChange> & { id: string; effectiveDate: string }): AcademicChange => ({
  admissionYearFrom: null,
  admissionYearTo: null,
  title: `테스트 항목 ${over.id}`,
  summary: '테스트용 요약',
  sourceUrl: 'https://example.com/notice',
  ...over,
})

// 2021학번, 2023년 1학기 휴학 → 2025년 1학기 복학 (2023-03-01 ~ 2025-03-01)
const QUERY: AcademicQuery = {
  admissionYear: 2021,
  leaveStart: { year: 2023, term: 1 },
  returnAt: { year: 2025, term: 1 },
}

describe('filterChanges: 기간', () => {
  it('휴학 시작 학기 ~ 복학 학기 시작일 사이 항목만, 시행일순', () => {
    const list = [
      change({ id: 'c', effectiveDate: '2024-09-01' }),
      change({ id: 'a', effectiveDate: '2023-09-01' }),
      change({ id: 'b', effectiveDate: '2024-03-01' }),
    ]
    expect(filterChanges(list, QUERY).map((c) => c.id)).toEqual(['a', 'b', 'c'])
  })

  it('휴학 시작 학기·복학 학기에 시행된 항목은 넣는다 (경계 포함)', () => {
    const list = [
      change({ id: 'leave', effectiveDate: '2023-03-01' }),
      change({ id: 'return', effectiveDate: '2025-03-01' }),
    ]
    expect(filterChanges(list, QUERY).map((c) => c.id)).toEqual(['leave', 'return'])
  })

  it('기간 밖 항목은 뺀다', () => {
    const list = [
      change({ id: 'before', effectiveDate: '2023-02-28' }),
      change({ id: 'after', effectiveDate: '2025-03-02' }),
      change({ id: 'way-after', effectiveDate: '2026-09-01' }),
    ]
    expect(filterChanges(list, QUERY)).toEqual([])
  })

  it('2학기 휴학·복학은 9월 1일 기준', () => {
    const q: AcademicQuery = { admissionYear: 2021, leaveStart: { year: 2022, term: 2 }, returnAt: { year: 2023, term: 2 } }
    const list = [
      change({ id: 'x', effectiveDate: '2022-08-31' }),
      change({ id: 'y', effectiveDate: '2022-09-01' }),
      change({ id: 'z', effectiveDate: '2023-09-01' }),
      change({ id: 'w', effectiveDate: '2023-09-02' }),
    ]
    expect(filterChanges(list, q).map((c) => c.id)).toEqual(['y', 'z'])
  })
})

describe('filterChanges: 적용 대상 입학년도', () => {
  it('내 입학년도가 범위 밖이면 뺀다', () => {
    const list = [
      change({ id: 'later-only', effectiveDate: '2024-03-01', admissionYearFrom: 2022 }),
      change({ id: 'earlier-only', effectiveDate: '2024-03-01', admissionYearTo: 2020 }),
      change({ id: 'range-out', effectiveDate: '2024-03-01', admissionYearFrom: 2018, admissionYearTo: 2019 }),
    ]
    expect(filterChanges(list, QUERY)).toEqual([])
  })

  it('범위 안이거나 전체 대상이면 넣는다', () => {
    const list = [
      change({ id: 'all', effectiveDate: '2024-03-01' }),
      change({ id: 'from', effectiveDate: '2024-03-01', admissionYearFrom: 2021 }),
      change({ id: 'to', effectiveDate: '2024-03-01', admissionYearTo: 2021 }),
      change({ id: 'range', effectiveDate: '2024-03-01', admissionYearFrom: 2020, admissionYearTo: 2022 }),
    ]
    expect(filterChanges(list, QUERY).map((c) => c.id)).toEqual(['all', 'from', 'range', 'to'])
  })

  it('appliesToAdmissionYear 경계', () => {
    const c = change({ id: 'r', effectiveDate: '2024-03-01', admissionYearFrom: 2020, admissionYearTo: 2022 })
    expect([2019, 2020, 2022, 2023].map((y) => appliesToAdmissionYear(c, y))).toEqual([false, true, true, false])
  })
})

describe('변경 사항이 없을 때', () => {
  it('데이터가 비어 있으면 빈 결과', () => {
    expect(filterChanges([], QUERY)).toEqual([])
    expect(groupByYear([])).toEqual([])
  })
})

describe('groupByYear', () => {
  it('시행 연도별로 묶는다', () => {
    const list = filterChanges(
      [
        change({ id: 'a', effectiveDate: '2023-09-01' }),
        change({ id: 'b', effectiveDate: '2024-03-01' }),
        change({ id: 'c', effectiveDate: '2024-09-01' }),
      ],
      QUERY,
    )
    expect(groupByYear(list).map((g) => [g.year, g.changes.map((c) => c.id)])).toEqual([
      [2023, ['a']],
      [2024, ['b', 'c']],
    ])
  })
})

describe('validateInput: 잘못된 입력', () => {
  const ok: AcademicInput = { admissionYear: '2021', leaveYear: '2023', leaveTerm: '1', returnYear: '2025', returnTerm: '1' }

  it('올바른 입력', () => {
    expect(validateInput(ok, 2026)).toEqual(QUERY)
  })

  it('입학년도 없음·범위 밖', () => {
    expect(validateInput({ ...ok, admissionYear: '' }, 2026)).toContain('입학년도')
    expect(validateInput({ ...ok, admissionYear: '1999' }, 2026)).toContain('입학년도')
    expect(validateInput({ ...ok, admissionYear: '2027' }, 2026)).toContain('입학년도')
    expect(validateInput({ ...ok, admissionYear: '20a1' }, 2026)).toContain('입학년도')
  })

  it('학기를 고르지 않음', () => {
    expect(validateInput({ ...ok, leaveTerm: '' }, 2026)).toContain('휴학 시작 시기')
    expect(validateInput({ ...ok, returnYear: '' }, 2026)).toContain('복학 시기')
    expect(validateInput({ ...ok, returnTerm: '3' }, 2026)).toContain('복학 시기')
  })

  it('입학 전 휴학', () => {
    expect(validateInput({ ...ok, leaveYear: '2020' }, 2026)).toBe('휴학 시작 시기는 입학년도 이후로 선택해 주세요')
  })

  it('복학이 휴학 시작과 같거나 앞선 학기', () => {
    const msg = '복학 시기는 휴학 시작 시기보다 뒤 학기로 선택해 주세요'
    expect(validateInput({ ...ok, returnYear: '2023', returnTerm: '1' }, 2026)).toBe(msg)
    expect(validateInput({ ...ok, leaveTerm: '2', returnYear: '2023', returnTerm: '1' }, 2026)).toBe(msg)
    expect(validateInput({ ...ok, leaveTerm: '1', returnYear: '2023', returnTerm: '2' }, 2026)).not.toBe(msg)
  })
})

describe('parseChanges: JSON 검사', () => {
  const valid = {
    id: 'ok',
    effectiveDate: '2024-03-01',
    admissionYearFrom: 2020,
    admissionYearTo: null,
    title: '제목',
    summary: '요약',
    sourceUrl: 'https://example.com/a',
  }

  it('형식에 맞는 항목만 남긴다', () => {
    const { changes, invalid } = parseChanges([
      valid,
      { ...valid, id: 'no-source', sourceUrl: '' },
      { ...valid, id: 'http', sourceUrl: 'http://example.com' },
      { ...valid, id: 'js', sourceUrl: 'javascript:alert(1)' },
      { ...valid, id: 'bad-date', effectiveDate: '2024-02-30' },
      { ...valid, id: 'reversed', admissionYearFrom: 2023, admissionYearTo: 2020 },
      { ...valid, id: 'no-title', title: ' ' },
      { ...valid },
      'not an object',
    ])
    expect(changes.map((c) => c.id)).toEqual(['ok'])
    expect(invalid).toEqual(['no-source', 'http', 'js', 'bad-date', 'reversed', 'no-title', 'ok', '#8'])
  })

  it('배열이 아니면 전부 무효', () => {
    expect(parseChanges({}).changes).toEqual([])
  })

  it('출처는 https만', () => {
    expect(isSafeSourceUrl('https://www.knu.ac.kr/')).toBe(true)
    expect(isSafeSourceUrl('http://www.knu.ac.kr/')).toBe(false)
    expect(isSafeSourceUrl('javascript:alert(1)')).toBe(false)
    expect(isSafeSourceUrl('knu.ac.kr')).toBe(false)
  })

  it('content/academic_changes.json의 모든 항목이 형식에 맞는다 (출처 포함)', () => {
    const { invalid } = parseChanges(rawChanges as unknown)
    expect(invalid).toEqual([])
  })
})

describe('표시', () => {
  it('학기 시작일', () => {
    expect(semesterStart({ year: 2024, term: 1 })).toBe('2024-03-01')
    expect(semesterStart({ year: 2024, term: 2 })).toBe('2024-09-01')
  })

  it('시행일', () => {
    expect(formatEffectiveDate('2025-03-01')).toBe('2025년 3월 1일')
  })

  it('적용 대상 학번', () => {
    const base = { id: 'x', effectiveDate: '2024-03-01' }
    expect(admissionTargetText(change(base))).toBe('전체 학번')
    expect(admissionTargetText(change({ ...base, admissionYearFrom: 2023 }))).toBe('2023학번부터')
    expect(admissionTargetText(change({ ...base, admissionYearTo: 2019 }))).toBe('2019학번까지')
    expect(admissionTargetText(change({ ...base, admissionYearFrom: 2020, admissionYearTo: 2022 }))).toBe('2020~2022학번')
    expect(admissionTargetText(change({ ...base, admissionYearFrom: 2021, admissionYearTo: 2021 }))).toBe('2021학번')
  })
})
