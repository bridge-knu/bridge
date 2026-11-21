// 진단 API(POST /diagnosis/start, /diagnosis/answer) 실패를 화면 동작별로 나눈다.
// 오류 코드(code)가 있으면 그것으로 나누고, 없거나 모르는 코드면 상태 코드와 detail 문구로 나눈다.
// (백엔드 오류 코드 적용 전 응답과 422 FastAPI 기본 응답에는 code가 없다)

import { ApiError, type ApiErrorCode } from '../api.ts'

/**
 * unauthorized: 토큰 없음·만료 → 로그인 화면
 * finished: 이미 끝난 진단 → 완료 화면 (다시 시작하면 결과가 지워짐)
 * mismatch: 지금 문제가 아닌 답 등 400 → 안내 + 다시 시작 버튼 (같은 답을 다시 내도 계속 실패함)
 * other: 그 밖의 오류 (422, 5xx, 네트워크 실패) → 안내만
 */
export type DiagnosisErrorKind = 'unauthorized' | 'finished' | 'mismatch' | 'other'

const KIND_BY_CODE: Partial<Record<ApiErrorCode, DiagnosisErrorKind>> = {
  UNAUTHORIZED: 'unauthorized',
  DIAGNOSIS_FINISHED: 'finished',
  QUESTION_MISMATCH: 'mismatch',
}

// code가 없는 응답용. backend/app/api/diagnosis.py의 400 detail 문구.
export const DIAGNOSIS_FINISHED_DETAIL = '진단이 이미 끝났어요'

export function classifyDiagnosisError(err: unknown): DiagnosisErrorKind {
  if (!(err instanceof ApiError)) return 'other'

  const byCode = err.code ? KIND_BY_CODE[err.code as ApiErrorCode] : undefined
  if (byCode) return byCode

  if (err.status === 401) return 'unauthorized'
  if (err.status === 400) return err.detail === DIAGNOSIS_FINISHED_DETAIL ? 'finished' : 'mismatch'
  return 'other'
}
