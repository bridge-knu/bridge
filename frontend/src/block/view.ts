// 블록 학습 화면의 작은 도우미: 에디터 초기 코드, 조회 오류 분류, 확인 문제 답 정리.

import { ApiError, type BlockDetail, type CheckAnswer, type CheckResult, type PracticeLang } from '../api.ts'

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

/** 채점 뒤 보기 표시: 정답 보기는 'answer'(파랑 ✓), 내가 고른 오답은 'wrong'(주황 !) */
export type ChoiceMark = 'answer' | 'wrong' | null

export function choiceMark(result: CheckResult | undefined, index: number): ChoiceMark {
  if (!result) return null
  if (index === result.answer) return 'answer'
  if (index === result.choice) return 'wrong'
  return null
}

/**
 * 채점 뒤 문제 아래 한 줄. 화면의 보기에는 번호가 없어서 정답은 보기 내용으로 알려 준다.
 * 보기가 코드·숫자라 이에요/예요가 틀릴 수 있어 조사 없이 "정답: ‘…’"로 쓴다.
 */
export function checkFeedback(result: CheckResult, choices: string[]): string {
  if (result.correct) return '정답이에요.'
  const text = choices[result.answer]
  const answer = text === undefined ? `정답: ${result.answer + 1}번째 보기` : `정답: ‘${text}’`
  return result.choice === null ? `답하지 않았어요. ${answer}` : `틀렸어요. ${answer}`
}

/** 채점한 문제 중 답을 바꿔서 표시가 지워진 문제가 있는지 (있으면 맞힌 개수 문구가 예전 값이다) */
export function gradingStale(results: CheckResult[] | undefined, graded: Record<string, CheckResult>): boolean {
  return (results ?? []).some((r) => graded[r.questionId] === undefined)
}

/** 완료 응답의 채점 결과를 문제 id로 찾을 수 있게 */
export function resultsById(results: CheckResult[] | undefined): Record<string, CheckResult> {
  return Object.fromEntries((results ?? []).map((r) => [r.questionId, r]))
}
