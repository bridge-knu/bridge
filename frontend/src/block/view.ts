// 블록 학습 화면의 작은 도우미: 에디터 초기 코드, 조회 오류 분류, 확인 문제 답 정리.

import { ApiError, type BlockDetail, type CheckAnswer, type PracticeLang } from '../api.ts'

/** 에디터 초기 코드: 서버에 저장된 코드가 있으면 그것, 없으면 starter */
export function initialCode(block: Pick<BlockDetail, 'savedCode' | 'practice'>): string {
  return block.savedCode ?? block.practice.starter
}

/** practice.lang → Monaco 언어 id */
export function editorLanguage(lang: PracticeLang): string {
  return lang === 'c' ? 'c' : 'python'
}

/**
 * unauthorized: 토큰 없음·만료 → 로그인 화면
 * notFound: 없는 블록 (404 BLOCK_NOT_FOUND)
 * other: 그 밖의 오류 (5xx, 네트워크 실패 등) → 안내 + 다시 시도
 */
export type BlockErrorKind = 'unauthorized' | 'notFound' | 'other'

export function classifyBlockError(err: unknown): BlockErrorKind {
  if (!(err instanceof ApiError)) return 'other'
  if (err.code === 'UNAUTHORIZED' || err.status === 401) return 'unauthorized'
  if (err.code === 'BLOCK_NOT_FOUND' || err.status === 404) return 'notFound'
  return 'other'
}

export function errorText(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.detail ?? '잠시 후 다시 시도해 주세요'
  if (err instanceof TypeError) return '서버에 연결할 수 없어요. 네트워크를 확인해 주세요'
  return fallback
}

/** 고른 답(문제 id → 보기 인덱스)을 완료 요청 형식으로. 화면의 문제 순서를 따르고, 답하지 않은 문제는 뺀다 */
export function toCheckAnswers(questionIds: string[], selected: Record<string, number | undefined>): CheckAnswer[] {
  return questionIds.flatMap((questionId) => {
    const choice = selected[questionId]
    return choice === undefined ? [] : [{ questionId, choice }]
  })
}
