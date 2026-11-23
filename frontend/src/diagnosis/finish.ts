// 진단 진행 표시와 완료 화면의 "왜 여기서 끝났는지" 한 줄.
// 엔진은 최대 문제 수(maxQuestions)까지 묻지만, 맞힌 개념의 바탕 개념은 건너뛰고
// 더 물어볼 개념이 없으면 그보다 일찍 끝낸다. "문제 3 / 10"처럼 보이면 10문제를 다 푸는 줄 알아서 따로 알려 준다.

/** 진단 중 진행 표시. 10문제를 다 푸는 게 아니라 최대 문제 수라는 걸 드러낸다 */
export function progressLabel(number: number, max: number): string {
  return `${number}번째 문제 · 최대 ${max}문제`
}

export interface FinishInput {
  /** 푼 문제 수 */
  answered: number
  /** 최대 문제 수 */
  max: number
  /** 이번 진단에서 맞힌 문제 수 */
  correct: number
}

/** 진단을 끝낸 이유 한 줄 */
export function finishReason({ answered, max, correct }: FinishInput): string {
  if (answered === 0) {
    return '이수 성적과 공백 기간으로 보면 필요한 개념을 이미 알고 있다고 추정돼서, 물어볼 문제 없이 끝났어요.'
  }
  if (answered >= max) {
    return `최대 ${max}문제를 모두 풀었어요. 묻지 않은 개념은 이수 성적과 공백 기간으로 추정했어요.`
  }
  const early = `${answered}문제로 일찍 끝났어요.`
  if (correct > 0) {
    return `${early} 맞힌 개념의 바탕 개념은 안다고 보고 건너뛰어서, 더 물어볼 개념이 남지 않았어요.`
  }
  return `${early} 바탕 개념까지 차례로 확인해서, 더 물어볼 개념이 남지 않았어요.`
}
