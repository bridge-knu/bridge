// 진단 결과 API(GET /diagnosis/result) 실패를 화면 동작별로 나눈다.
// 오류 코드(code)가 있으면 그것으로 나누고, 없거나 모르는 코드면 상태 코드로 나눈다.
// (백엔드 오류 코드 적용 전 응답에는 code가 없다)

import { ApiError, type ApiErrorCode } from '../api.ts'

/**
 * unauthorized: 토큰 없음·만료 → 로그인 화면
 * notFinished: 진단을 끝내지 않음 → 안내 후 진단 화면으로
 * other: 그 밖의 오류 (5xx, 네트워크 실패 등) → 안내 + 다시 불러오기
 */
export type ResultErrorKind = 'unauthorized' | 'notFinished' | 'other'

const KIND_BY_CODE: Partial<Record<ApiErrorCode, ResultErrorKind>> = {
  UNAUTHORIZED: 'unauthorized',
  DIAGNOSIS_NOT_FINISHED: 'notFinished',
}

export function classifyResultError(err: unknown): ResultErrorKind {
  if (!(err instanceof ApiError)) return 'other'

  const byCode = err.code ? KIND_BY_CODE[err.code as ApiErrorCode] : undefined
  if (byCode) return byCode

  if (err.status === 401) return 'unauthorized'
  // GET /diagnosis/result의 400은 "진단 미완료" 하나뿐이다 (docs/api-contract.md)
  if (err.status === 400) return 'notFinished'
  return 'other'
}

/** other 오류의 안내 문구 */
export function resultErrorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.detail ?? '잠시 후 다시 시도해 주세요'
  if (err instanceof TypeError) return '서버에 연결할 수 없어요. 네트워크를 확인해 주세요'
  return '결과를 불러오지 못했어요. 다시 시도해 주세요'
}
