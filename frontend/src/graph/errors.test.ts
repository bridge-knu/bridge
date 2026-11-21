import { describe, expect, it } from 'vitest'
import { ApiError } from '../api.ts'
import { classifyResultError, resultErrorMessage } from './errors.ts'

const apiError = (status: number, body: unknown) => new ApiError(status, body)

describe('classifyResultError', () => {
  it('code가 있으면 code로 나눈다', () => {
    expect(classifyResultError(apiError(401, { detail: 'x', code: 'UNAUTHORIZED' }))).toBe('unauthorized')
    expect(classifyResultError(apiError(400, { detail: 'x', code: 'DIAGNOSIS_NOT_FINISHED' }))).toBe('notFinished')
  })

  it('code가 없으면 상태 코드로 나눈다', () => {
    expect(classifyResultError(apiError(401, { detail: 'x' }))).toBe('unauthorized')
    expect(classifyResultError(apiError(400, { detail: 'x' }))).toBe('notFinished')
  })

  it('모르는 code는 상태 코드로 나눈다', () => {
    expect(classifyResultError(apiError(400, { detail: 'x', code: 'SOMETHING_NEW' }))).toBe('notFinished')
    expect(classifyResultError(apiError(503, { detail: 'x', code: 'SOMETHING_NEW' }))).toBe('other')
  })

  it('5xx, 네트워크 실패, 그 밖의 값은 other', () => {
    expect(classifyResultError(apiError(500, 'Internal Server Error'))).toBe('other')
    expect(classifyResultError(apiError(503, { detail: '잠시 후 다시 시도해 주세요' }))).toBe('other')
    expect(classifyResultError(new TypeError('Failed to fetch'))).toBe('other')
    expect(classifyResultError('oops')).toBe('other')
  })
})

describe('resultErrorMessage', () => {
  it('detail이 있으면 그대로, 없으면 기본 문구', () => {
    expect(resultErrorMessage(apiError(503, { detail: 'DB 점검 중이에요' }))).toBe('DB 점검 중이에요')
    expect(resultErrorMessage(apiError(500, 'Internal Server Error'))).toBe('잠시 후 다시 시도해 주세요')
  })

  it('네트워크 실패와 알 수 없는 오류', () => {
    expect(resultErrorMessage(new TypeError('Failed to fetch'))).toContain('서버에 연결할 수 없어요')
    expect(resultErrorMessage(new Error('x'))).toContain('결과를 불러오지 못했어요')
  })
})
