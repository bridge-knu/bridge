// 진단 중에 "왜 이 문제를 내는지" 한 줄로 알려 주는 문구.
// 엔진(백엔드)은 맞히면 그 개념의 선수 개념을 안다고 보고 건너뛰고, 틀리면 선수 개념을 먼저 묻는다.
// 그 판단을 화면에서도 보이게 하려고, 직전 문제의 정답 여부와 다음 문제의 개념으로 문구를 만든다.
// 선수 관계는 content/concepts.json에서 읽는다 (빌드할 때 번들에 들어감).
import rawConcepts from '../../../content/concepts.json'

interface ConceptRef {
  id: string
  prereqs: string[]
}

const prereqsById = new Map<string, string[]>((rawConcepts as ConceptRef[]).map((c) => [c.id, c.prereqs]))

/** 개념의 모든 선수 개념 (선수의 선수까지) */
export function ancestorsOf(conceptId: string): Set<string> {
  const seen = new Set<string>()
  const stack = [...(prereqsById.get(conceptId) ?? [])]
  while (stack.length > 0) {
    const id = stack.pop() as string
    if (seen.has(id)) continue
    seen.add(id)
    stack.push(...(prereqsById.get(id) ?? []))
  }
  return seen
}

// "성능 분석(Big-O)"처럼 괄호가 붙은 이름은 괄호 앞 글자로 받침을 본다
function hasFinalConsonant(word: string): boolean {
  const base = word.replace(/\s*\(.*\)\s*$/, '').trim()
  const last = base.charCodeAt(base.length - 1)
  if (last < 0xac00 || last > 0xd7a3) return false
  return (last - 0xac00) % 28 !== 0
}

const quote = (name: string) => `‘${name}’`
/** ‘포인터’를, ‘배열’을 */
export const withEulReul = (name: string) => quote(name) + (hasFinalConsonant(name) ? '을' : '를')
/** ‘포인터’는, ‘배열’은 */
export const withEunNeun = (name: string) => quote(name) + (hasFinalConsonant(name) ? '은' : '는')

export interface ReasonConcept {
  concept: string
  conceptName: string
}

export interface ReasonInput {
  /** 방금 푼 문제의 개념. 첫 문제면 null */
  prev: ReasonConcept | null
  /** 방금 낸 답의 정답 여부. 첫 문제면 null */
  correct: boolean | null
  /** 지금 풀 문제의 개념. 진단이 끝났으면 null */
  next: ReasonConcept | null
}

/** 지금 문제를 내는 이유. 진단이 끝났으면 null */
export function diagnosisReason({ prev, correct, next }: ReasonInput): string | null {
  if (!next) return null

  if (!prev || correct === null) {
    return `목표 과목에 가까운 ${quote(next.conceptName)}부터 물어볼게요. 맞히면 그 바탕 개념은 건너뛰고, 틀리면 한 단계씩 내려가요.`
  }

  const ancestors = ancestorsOf(prev.concept)

  if (correct) {
    const skipped = ancestors.size > 0 ? ` 그 바탕 개념 ${ancestors.size}개는 안다고 보고 건너뛰었어요.` : ''
    return `${quote(prev.conceptName)} 정답!${skipped} 이어서 ${withEulReul(next.conceptName)} 확인할게요.`
  }

  const marked = `${withEunNeun(prev.conceptName)} 다시 볼 개념으로 표시했어요.`
  if (ancestors.has(next.concept)) {
    return `${marked} 그 바탕이 되는 ${withEulReul(next.conceptName)} 확인할게요.`
  }
  return `${marked} 이어서 ${withEulReul(next.conceptName)} 확인할게요.`
}
