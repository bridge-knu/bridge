// 진단 문제를 가져오는 곳. 화면(DiagnosisPage)은 DiagnosisSource만 알고,
// 문제가 어디서 오는지는 모른다.
//
// 지금은 진단 API 규격이 확정되지 않아 content/questions.json을 순서대로 내는
// 로컬 소스를 쓴다. API가 확정되면 api.ts의 startDiagnosis/answerDiagnosis를 부르는
// 소스를 만들어 아래 diagnosisSource만 바꾸면 된다.
// 아래 타입은 화면 내부용이며 API 규격이 아니다.

import rawQuestions from '../../../content/questions.json'

/** 화면에 보여줄 문제. questions.json의 필드에서 정답(answer)을 뺀 것. */
export interface DiagnosisQuestion {
  id: string
  concept: string
  type: 'choice'
  prompt: string
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
}

export interface DiagnosisSource {
  start(): Promise<DiagnosisStep>
  /** choice: choices의 0부터 시작하는 인덱스 */
  answer(questionId: string, choice: number): Promise<DiagnosisStep>
}

interface RawQuestion {
  id: string
  concept: string
  type?: string
  prompt: string
  code?: string | null
  choices: string[]
}

// 정답은 복사하지 않는다. 화면 코드가 정답을 볼 수 없게 하기 위함.
function toQuestion(q: RawQuestion): DiagnosisQuestion {
  return {
    id: q.id,
    concept: q.concept,
    type: 'choice',
    prompt: q.prompt,
    ...(q.code ? { code: q.code } : {}),
    choices: [...q.choices],
  }
}

// questions.json의 문제를 처음부터 순서대로 낸다. 채점·적응형 진행은 하지 않는다
// (그건 백엔드 엔진의 일이다). 답은 메모리에만 기록한다.
export function createLocalSource(raw: RawQuestion[]): DiagnosisSource {
  const questions = raw.map(toQuestion)
  let index = 0
  const answers: { questionId: string; choice: number }[] = []

  const step = (): DiagnosisStep => ({
    question: questions[index] ?? null,
    number: Math.min(index + 1, questions.length),
    total: questions.length,
  })

  return {
    async start() {
      index = 0
      answers.length = 0
      return step()
    },
    async answer(questionId, choice) {
      if (questions[index]?.id !== questionId) throw new Error('지금 문제가 아닌 답이 들어왔어요')
      answers.push({ questionId, choice })
      index += 1
      return step()
    },
  }
}

export const diagnosisSource: DiagnosisSource = createLocalSource(rawQuestions as RawQuestion[])
