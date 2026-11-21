import { describe, expect, it } from 'vitest'
import { ApiError } from '../api.ts'
import { classifyDiagnosisError } from './errors.ts'

const apiError = (status: number, body: unknown) => new ApiError(status, body)

describe('ApiError.code', () => {
  it('문자열 code를 꺼내고 detail도 그대로 둔다', () => {
    const err = apiError(400, { detail: '진단이 이미 끝났어요', code: 'DIAGNOSIS_FINISHED' })
    expect(err.code).toBe('DIAGNOSIS_FINISHED')
    expect(err.detail).toBe('진단이 이미 끝났어요')
    expect(err.message).toBe('진단이 이미 끝났어요')
  })

  it('code가 없거나 문자열이 아니면 null', () => {
    expect(apiError(400, { detail: 'x' }).code).toBeNull()
    expect(apiError(400, { detail: 'x', code: 1 }).code).toBeNull()
    expect(apiError(400, { detail: 'x', code: '' }).code).toBeNull()
    expect(apiError(500, 'Internal Server Error').code).toBeNull()
    expect(apiError(500, null).code).toBeNull()
  })

  it('422 FastAPI 기본 응답은 detail·code 모두 null', () => {
    const err = apiError(422, { detail: [{ type: 'greater_than_equal', loc: ['body', 'choice'], msg: '...' }] })
    expect(err.detail).toBeNull()
    expect(err.code).toBeNull()
  })
})

describe('classifyDiagnosisError: code 우선', () => {
  it.each([
    ['UNAUTHORIZED', 401, 'unauthorized'],
    ['DIAGNOSIS_FINISHED', 400, 'finished'],
    ['QUESTION_MISMATCH', 400, 'mismatch'],
  ] as const)('%s → %s', (code, status, kind) => {
    expect(classifyDiagnosisError(apiError(status, { detail: '안내', code }))).toBe(kind)
  })

  it('code가 있으면 detail 문구가 달라도 code를 따른다', () => {
    // 문구가 바뀌어도 code로 완료 화면에 간다
    expect(classifyDiagnosisError(apiError(400, { detail: '이미 끝난 진단이에요', code: 'DIAGNOSIS_FINISHED' }))).toBe('finished')
    // 완료 문구가 와도 code가 불일치면 다시 시작
    expect(classifyDiagnosisError(apiError(400, { detail: '진단이 이미 끝났어요', code: 'QUESTION_MISMATCH' }))).toBe('mismatch')
  })

  it('모르는 code는 상태 코드·detail로 판단한다', () => {
    expect(classifyDiagnosisError(apiError(400, { detail: '진단이 이미 끝났어요', code: 'NEW_CODE' }))).toBe('finished')
    expect(classifyDiagnosisError(apiError(400, { detail: '다른 문구', code: 'NEW_CODE' }))).toBe('mismatch')
    expect(classifyDiagnosisError(apiError(401, { detail: '로그인', code: 'NEW_CODE' }))).toBe('unauthorized')
    expect(classifyDiagnosisError(apiError(500, { detail: '오류', code: 'NEW_CODE' }))).toBe('other')
  })
})

describe('classifyDiagnosisError: code 없을 때 기존 동작 (detail fallback)', () => {
  it('401 → unauthorized', () => {
    expect(classifyDiagnosisError(apiError(401, { detail: '로그인이 필요해요' }))).toBe('unauthorized')
    expect(classifyDiagnosisError(apiError(401, null))).toBe('unauthorized')
  })

  it('400 "진단이 이미 끝났어요" → finished', () => {
    expect(classifyDiagnosisError(apiError(400, { detail: '진단이 이미 끝났어요' }))).toBe('finished')
  })

  it('그 밖의 400 → mismatch (다시 시작)', () => {
    expect(classifyDiagnosisError(apiError(400, { detail: '지금 풀고 있는 문제가 아니에요' }))).toBe('mismatch')
    expect(classifyDiagnosisError(apiError(400, null))).toBe('mismatch')
  })

  it('422·5xx·네트워크 실패 → other', () => {
    expect(classifyDiagnosisError(apiError(422, { detail: [{ msg: '...' }] }))).toBe('other')
    expect(classifyDiagnosisError(apiError(500, 'Internal Server Error'))).toBe('other')
    expect(classifyDiagnosisError(new TypeError('Failed to fetch'))).toBe('other')
    expect(classifyDiagnosisError(new Error('x'))).toBe('other')
  })
})
