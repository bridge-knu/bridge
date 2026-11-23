import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ApiError,
  GRADES,
  getProfile,
  saveProfile,
  setAuthToken,
  type CompletedCourse,
  type CourseCode,
  type Profile,
} from '../api.ts'
import { NOT_TAKEN, emptyForm, profileToForm, type FormValues, type GradeSelection } from '../profile/form.ts'

// 과목 id는 content/concepts.json의 course 값과 같다.
const COURSES: { id: CourseCode; name: string }[] = [
  { id: 'C', name: 'C 프로그래밍' },
  { id: 'DS', name: '자료구조' },
]

// 백엔드 Profile 스키마(PR #28)의 범위와 같다. 벗어나면 422가 난다.
const GAP_MONTHS_MAX = 120
const DAILY_MINUTES_MIN = 30
const DAILY_MINUTES_MAX = 600

// 로컬 시간 기준 오늘 날짜 (YYYY-MM-DD)
function today(): string {
  const d = new Date()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

// 문제가 없으면 Profile, 있으면 안내 문구를 돌려준다.
function toProfile(v: FormValues): Profile | string {
  const gapMonths = Number(v.gapMonths)
  if (v.gapMonths.trim() === '' || !Number.isInteger(gapMonths) || gapMonths < 0 || gapMonths > GAP_MONTHS_MAX) {
    return `공백 기간은 0 이상 ${GAP_MONTHS_MAX} 이하의 정수(개월)로 입력해 주세요`
  }
  const targetCourse = COURSES.find((c) => c.id === v.targetCourse)?.id
  if (!targetCourse) {
    return '목표 과목을 선택해 주세요'
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(v.returnDate)) {
    return '복학 예정일을 선택해 주세요'
  }
  if (v.returnDate <= today()) {
    return '복학 예정일은 내일 이후 날짜로 선택해 주세요'
  }
  const dailyMinutes = Number(v.dailyMinutes)
  if (
    v.dailyMinutes.trim() === '' ||
    !Number.isInteger(dailyMinutes) ||
    dailyMinutes < DAILY_MINUTES_MIN ||
    dailyMinutes > DAILY_MINUTES_MAX
  ) {
    return `하루 학습 시간은 ${DAILY_MINUTES_MIN}분 이상 ${DAILY_MINUTES_MAX}분 이하의 정수로 입력해 주세요`
  }

  // 선택한 성적을 그대로 보낸다 (변환하지 않음). 미수강만 뺀다.
  const completedCourses: CompletedCourse[] = []
  for (const course of COURSES) {
    const grade = v.grades[course.id]
    if (grade !== NOT_TAKEN) completedCourses.push({ course: course.id, grade })
  }

  return { completedCourses, gapMonths, targetCourse, returnDate: v.returnDate, dailyMinutes }
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.detail) return err.detail
    return '저장하지 못했어요. 잠시 후 다시 시도해 주세요'
  }
  return '서버에 연결할 수 없어요. 네트워크를 확인해 주세요'
}

export default function ProfilePage() {
  const navigate = useNavigate()
  const [values, setValues] = useState<FormValues>(() => emptyForm(COURSES.map((c) => c.id)))
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  // 저장된 프로필을 불러와 채웠는지 (안내 문구용)
  const [loadedSaved, setLoadedSaved] = useState(false)
  // 불러오기 전에 사용자가 먼저 입력을 시작했으면 덮어쓰지 않는다
  const touched = useRef(false)

  // 다시 들어왔을 때 저장된 값을 채워 보여 준다. 아직 입력 전(404)이거나 실패하면 지금처럼 빈 양식
  useEffect(() => {
    let cancelled = false
    getProfile()
      .then((profile) => {
        if (cancelled || touched.current) return
        setValues(profileToForm(profile, COURSES.map((c) => c.id)))
        setLoadedSaved(true)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 401) {
          setAuthToken(null)
          navigate('/login', { replace: true })
        }
      })
    return () => {
      cancelled = true
    }
  }, [navigate])

  function update<K extends keyof FormValues>(key: K, value: FormValues[K]) {
    touched.current = true
    setValues((prev) => ({ ...prev, [key]: value }))
  }

  function updateGrade(courseId: string, grade: GradeSelection) {
    touched.current = true
    setValues((prev) => ({ ...prev, grades: { ...prev.grades, [courseId]: grade } }))
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (loading) return

    const profile = toProfile(values)
    if (typeof profile === 'string') {
      setError(profile)
      return
    }

    setError(null)
    setLoading(true)
    try {
      await saveProfile(profile)
      navigate('/diagnosis')
    } catch (err) {
      // 토큰이 없거나 만료됨 (새로고침하면 메모리 토큰이 사라짐) → 다시 로그인
      if (err instanceof ApiError && err.status === 401) {
        setAuthToken(null)
        navigate('/login', { replace: true })
        return
      }
      setError(errorMessage(err))
      setLoading(false)
    }
  }

  return (
    <section className="form-page">
      <h1>프로필 입력</h1>
      <p className="form-hint">
        {loadedSaved
          ? '저장된 프로필을 불러왔어요. 바꿔서 저장하면 학습 계획을 새 값으로 다시 짜요.'
          : '입력한 내용으로 진단 시작점과 학습 계획을 정해요.'}
      </p>

      <form className="form" onSubmit={handleSubmit} noValidate>
        <fieldset disabled={loading}>
          <legend>이수 과목과 성적</legend>
          {COURSES.map((course) => (
            <label key={course.id}>
              {course.name}
              <select
                name={`grade-${course.id}`}
                value={values.grades[course.id]}
                onChange={(e) => updateGrade(course.id, e.target.value as GradeSelection)}
              >
                <option value={NOT_TAKEN}>미수강</option>
                {GRADES.map((g) => (
                  <option key={g} value={g}>
                    {g}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </fieldset>

        <label>
          공백 기간 (개월)
          <input
            type="number"
            name="gapMonths"
            autoComplete="off"
            inputMode="numeric"
            min={0}
            max={GAP_MONTHS_MAX}
            step={1}
            value={values.gapMonths}
            onChange={(e) => update('gapMonths', e.target.value)}
            disabled={loading}
          />
        </label>

        <label>
          목표 과목
          <select
            name="targetCourse"
            value={values.targetCourse}
            onChange={(e) => update('targetCourse', e.target.value)}
            disabled={loading}
          >
            <option value="">선택해 주세요</option>
            {COURSES.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          복학 예정일
          <input
            type="date"
            name="returnDate"
            autoComplete="off"
            min={today()}
            value={values.returnDate}
            onChange={(e) => update('returnDate', e.target.value)}
            disabled={loading}
          />
        </label>

        <label>
          하루 학습 가능 시간 (분)
          <input
            type="number"
            name="dailyMinutes"
            autoComplete="off"
            inputMode="numeric"
            min={DAILY_MINUTES_MIN}
            max={DAILY_MINUTES_MAX}
            step={30}
            value={values.dailyMinutes}
            onChange={(e) => update('dailyMinutes', e.target.value)}
            disabled={loading}
          />
        </label>

        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}

        <button type="submit" disabled={loading}>
          {loading ? '저장 중…' : '저장하고 진단 시작'}
        </button>
      </form>
    </section>
  )
}
