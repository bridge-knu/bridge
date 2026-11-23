// 진단 문제를 가져오는 곳. 화면(DiagnosisPage)은 DiagnosisSource만 알고,
// 문제가 어디서 오는지는 모른다.
//
// 백엔드 진단 API(POST /diagnosis/start, /diagnosis/answer)를 부르고,
// 응답(api.ts의 DiagnosisStep)을 아래의 화면용 형태로 바꿔서 돌려준다.
// 채점과 다음 문제 선택은 백엔드가 한다. 직전 답의 정답 여부(correct)는 "왜 이 문제인지" 안내 문구에만 쓴다.
// 아래 타입은 화면 내부용이며 API 규격이 아니다. API 규격은 api.ts에 있다.

import {
  answerDiagnosis,
  startDiagnosis,
  type DiagnosisStep as ApiDiagnosisStep,
  type QuestionOut,
} from '../api.ts'

/** 화면에 보여줄 문제 */
export interface DiagnosisQuestion {
  id: string
  /** 개념 id (API의 conceptId) */
  concept: string
  /** 개념 이름 (API의 conceptName) */
  conceptName: string
  type: 'choice'
  prompt: string
  /** 코드 문제일 때만 있다 */
  code?: string
  choices: string[]
}

/** 지금 풀 문제와 진행 상황. question이 null이면 진단이 끝났다. */
export interface DiagnosisStep {
  question: DiagnosisQuestion | null
  /** 지금까지 낸 문제 수 (지금 문제 포함) */
  number: number
  /** 최대 문제 수 */
  total: number
  /** 방금 낸 답의 정답 여부 (첫 문제면 null) */
  correct: boolean | null
}

export interface DiagnosisSource {
  start(): Promise<DiagnosisStep>
  /** choice: choices의 0부터 시작하는 인덱스 */
  answer(questionId: string, choice: number): Promise<DiagnosisStep>
}

function toQuestion(q: QuestionOut): DiagnosisQuestion {
  return {
    id: q.id,
    concept: q.conceptId,
    conceptName: q.conceptName,
    type: 'choice',
    prompt: q.prompt,
    ...(q.code ? { code: q.code } : {}),
    choices: [...q.choices],
  }
}

// answeredCount는 지금 문제 전까지 답한 수라서, 지금 문제 번호는 +1이다.
export function toStep(res: ApiDiagnosisStep): DiagnosisStep {
  const question = res.done || !res.question ? null : toQuestion(res.question)
  return {
    question,
    number: question ? Math.min(res.answeredCount + 1, res.maxQuestions) : res.answeredCount,
    total: res.maxQuestions,
    correct: res.correct,
  }
}

export function createApiSource(): DiagnosisSource {
  return {
    async start() {
      return toStep(await startDiagnosis())
    },
    async answer(questionId, choice) {
      return toStep(await answerDiagnosis(questionId, choice))
    },
  }
}

export const diagnosisSource: DiagnosisSource = createApiSource()
