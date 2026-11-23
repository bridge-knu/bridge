import { describe, expect, it } from 'vitest'
import { emptyForm, profileToForm } from './form.ts'

describe('저장된 프로필로 양식 채우기', () => {
  it('빈 양식은 모든 과목이 미수강', () => {
    expect(emptyForm(['C', 'DS'])).toEqual({
      grades: { C: '', DS: '' },
      gapMonths: '',
      targetCourse: '',
      returnDate: '',
      dailyMinutes: '',
    })
  })

  it('이수한 과목은 성적, 숫자는 문자열로', () => {
    const form = profileToForm(
      {
        completedCourses: [{ course: 'C', grade: 'B0' }],
        gapMonths: 24,
        targetCourse: 'DS',
        returnDate: '2027-03-02',
        dailyMinutes: 60,
      },
      ['C', 'DS'],
    )
    expect(form).toEqual({
      grades: { C: 'B0', DS: '' },
      gapMonths: '24',
      targetCourse: 'DS',
      returnDate: '2027-03-02',
      dailyMinutes: '60',
    })
  })

  it('목록에 없는 과목은 무시', () => {
    const form = profileToForm(
      {
        completedCourses: [{ course: 'C', grade: 'A+' }],
        gapMonths: 0,
        targetCourse: 'C',
        returnDate: '2027-01-01',
        dailyMinutes: 30,
      },
      ['DS'],
    )
    expect(form.grades).toEqual({ DS: '' })
  })
})
