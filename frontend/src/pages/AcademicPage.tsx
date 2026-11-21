import { useState, type FormEvent } from 'react'
import rawChanges from '../../../content/academic_changes.json'
import ChangeCard from '../academic/ChangeCard.tsx'
import {
  ADMISSION_YEAR_MIN,
  filterChanges,
  groupByYear,
  parseChanges,
  semesterText,
  validateInput,
  type AcademicChange,
  type AcademicInput,
  type AcademicQuery,
} from '../academic/changes.ts'

// 형식이 틀린 항목은 화면에 내지 않는다 (src/academic/changes.test.ts가 실제 JSON을 검사함).
const { changes: ALL_CHANGES } = parseChanges(rawChanges as unknown)

const THIS_YEAR = new Date().getFullYear()

function years(from: number, to: number): number[] {
  const list: number[] = []
  for (let y = to; y >= from; y -= 1) list.push(y)
  return list
}

const ADMISSION_YEARS = years(ADMISSION_YEAR_MIN, THIS_YEAR)
const LEAVE_YEARS = years(ADMISSION_YEAR_MIN, THIS_YEAR)
// 복학은 앞으로의 계획일 수 있어서 2년 뒤까지
const RETURN_YEARS = years(ADMISSION_YEAR_MIN, THIS_YEAR + 2)

const EMPTY: AcademicInput = { admissionYear: '', leaveYear: '', leaveTerm: '', returnYear: '', returnTerm: '' }

function SemesterSelect({
  label,
  yearOptions,
  year,
  term,
  onYear,
  onTerm,
}: {
  label: string
  yearOptions: number[]
  year: string
  term: string
  onYear: (v: string) => void
  onTerm: (v: string) => void
}) {
  return (
    <fieldset>
      <legend>{label}</legend>
      <div className="academic-semester">
        <label>
          연도
          <select value={year} onChange={(e) => onYear(e.target.value)}>
            <option value="">선택</option>
            {yearOptions.map((y) => (
              <option key={y} value={y}>
                {y}년
              </option>
            ))}
          </select>
        </label>
        <label>
          학기
          <select value={term} onChange={(e) => onTerm(e.target.value)}>
            <option value="">선택</option>
            <option value="1">1학기</option>
            <option value="2">2학기</option>
          </select>
        </label>
      </div>
    </fieldset>
  )
}

function Results({ query, changes }: { query: AcademicQuery; changes: AcademicChange[] }) {
  const period = `${semesterText(query.leaveStart)} 휴학 → ${semesterText(query.returnAt)} 복학`

  if (ALL_CHANGES.length === 0) {
    return (
      <p className="academic-empty">
        아직 등록된 학사 변경 정보가 없어요. 학교 공식 공지로 확인한 내용만 올리고 있으니, 그전까지는 학과
        사무실이나 학사 공지를 확인해 주세요.
      </p>
    )
  }

  if (changes.length === 0) {
    return (
      <>
        <p className="form-hint">{period}</p>
        <p className="academic-empty">
          이 기간에 {query.admissionYear}학번에 해당하는 학사 변경 사항이 없어요. 등록된 항목은 공식 공지로 확인한
          것만이라, 자세한 내용은 학사 공지도 함께 확인해 주세요.
        </p>
      </>
    )
  }

  return (
    <>
      <p className="form-hint">
        {period} · {query.admissionYear}학번 기준 <strong>{changes.length}건</strong>
      </p>
      <ol className="academic-timeline">
        {groupByYear(changes).map((group) => (
          <li key={group.year} className="academic-year">
            <h2>{group.year}년</h2>
            <ol>
              {group.changes.map((c) => (
                <li key={c.id}>
                  <ChangeCard change={c} />
                </li>
              ))}
            </ol>
          </li>
        ))}
      </ol>
    </>
  )
}

export default function AcademicPage() {
  const [values, setValues] = useState<AcademicInput>(EMPTY)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState<AcademicQuery | null>(null)

  const update = (key: keyof AcademicInput) => (value: string) => setValues((v) => ({ ...v, [key]: value }))

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const result = validateInput(values, THIS_YEAR)
    if (typeof result === 'string') {
      setError(result)
      setQuery(null)
      return
    }
    setError(null)
    setQuery(result)
  }

  return (
    <section className="academic-page">
      <h1>학사 안내</h1>
      <p className="form-hint">
        입학년도와 휴학·복학 시기를 고르면, 학교를 떠나 있던 동안 바뀐 학사 제도를 공식 공지와 함께 보여 드려요.
      </p>

      <form className="form academic-form" onSubmit={handleSubmit} noValidate>
        <label>
          입학년도
          <select value={values.admissionYear} onChange={(e) => update('admissionYear')(e.target.value)}>
            <option value="">선택</option>
            {ADMISSION_YEARS.map((y) => (
              <option key={y} value={y}>
                {y}년 ({y}학번)
              </option>
            ))}
          </select>
        </label>
        <SemesterSelect
          label="휴학 시작 시기"
          yearOptions={LEAVE_YEARS}
          year={values.leaveYear}
          term={values.leaveTerm}
          onYear={update('leaveYear')}
          onTerm={update('leaveTerm')}
        />
        <SemesterSelect
          label="복학 시기"
          yearOptions={RETURN_YEARS}
          year={values.returnYear}
          term={values.returnTerm}
          onYear={update('returnYear')}
          onTerm={update('returnTerm')}
        />
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <button type="submit">바뀐 제도 보기</button>
      </form>

      {/* 결과가 바뀌면 스크린리더가 읽도록 live 영역은 항상 둔다 */}
      <div className="academic-results" aria-live="polite">
        {query && <Results query={query} changes={filterChanges(ALL_CHANGES, query)} />}
      </div>
    </section>
  )
}
