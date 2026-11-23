// 프로필 화면 양식 값. 저장된 프로필(GET /profile)을 양식 값으로 바꾼다.

import type { CourseCode, Grade, Profile } from '../api.ts'

/** 드롭다운의 "미수강" 값. 이 값인 과목은 completedCourses에서 뺀다. */
export const NOT_TAKEN = ''

export type GradeSelection = Grade | typeof NOT_TAKEN

/** 입력칸은 문자열로 들고 있다가 저장할 때 숫자로 바꾼다. */
export interface FormValues {
  grades: Record<string, GradeSelection>
  gapMonths: string
  targetCourse: string
  returnDate: string
  dailyMinutes: string
}

export function emptyForm(courseIds: CourseCode[]): FormValues {
  return {
    grades: Object.fromEntries(courseIds.map((id) => [id, NOT_TAKEN])),
    gapMonths: '',
    targetCourse: '',
    returnDate: '',
    dailyMinutes: '',
  }
}

/** 저장된 프로필로 양식을 채운다. 목록에 없는 과목은 무시하고, 이수하지 않은 과목은 미수강으로 둔다. */
export function profileToForm(profile: Profile, courseIds: CourseCode[]): FormValues {
  const form = emptyForm(courseIds)
  for (const c of profile.completedCourses) {
    if (c.course in form.grades) form.grades[c.course] = c.grade
  }
  return {
    ...form,
    gapMonths: String(profile.gapMonths),
    targetCourse: profile.targetCourse,
    returnDate: profile.returnDate,
    dailyMinutes: String(profile.dailyMinutes),
  }
}
