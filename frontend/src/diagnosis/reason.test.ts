import { describe, expect, it } from 'vitest'
import { ancestorsOf, diagnosisReason, reasonTone, withEulReul, withEunNeun } from './reason.ts'

const pointer = { concept: 'pointer', conceptName: '포인터' }
const array = { concept: 'array', conceptName: '배열' }
const dynamicAlloc = { concept: 'dynamic_alloc', conceptName: '동적 할당' }
const recursion = { concept: 'recursion', conceptName: '재귀' }

describe('ancestorsOf', () => {
  it('선수의 선수까지 모은다', () => {
    const a = ancestorsOf('pointer')
    expect(a.has('array')).toBe(true)
    expect(a.has('variable')).toBe(true)
    expect(a.has('pointer')).toBe(false)
  })

  it('선수 개념이 없으면 빈 집합', () => {
    expect(ancestorsOf('variable').size).toBe(0)
  })
})

describe('조사', () => {
  it('받침에 따라 을/를, 은/는을 붙인다', () => {
    expect(withEulReul('배열')).toBe('‘배열’을')
    expect(withEulReul('포인터')).toBe('‘포인터’를')
    expect(withEunNeun('동적 할당')).toBe('‘동적 할당’은')
    expect(withEunNeun('재귀')).toBe('‘재귀’는')
  })

  it('괄호가 붙은 이름은 괄호 앞 글자로 본다', () => {
    expect(withEulReul('성능 분석(Big-O)')).toBe('‘성능 분석(Big-O)’을')
    expect(withEulReul('큐(원형 큐)')).toBe('‘큐(원형 큐)’를')
  })
})

describe('diagnosisReason', () => {
  it('첫 문제는 어디서 시작하는지 알려 준다', () => {
    const text = diagnosisReason({ prev: null, correct: null, next: dynamicAlloc })
    expect(text).toContain('‘동적 할당’부터 물어볼게요')
  })

  it('맞히면 바탕 개념은 더 묻지 않는다고 알려 준다 (개수는 세지 않음)', () => {
    const text = diagnosisReason({ prev: pointer, correct: true, next: recursion })
    expect(text).toBe('‘포인터’ 정답! 그 바탕 개념은 안다고 보고 더 묻지 않아요. 이어서 ‘재귀’를 확인할게요.')
    expect(text).not.toMatch(/\d+개/)
  })

  it('바탕 개념이 없는 개념을 맞히면 그 문장은 뺀다', () => {
    const variable = { concept: 'variable', conceptName: '변수' }
    const text = diagnosisReason({ prev: variable, correct: true, next: array })
    expect(text).toBe('‘변수’ 정답! 이어서 ‘배열’을 확인할게요.')
  })

  it('틀리고 다음이 그 바탕 개념이면 내려간다고 알려 준다', () => {
    const text = diagnosisReason({ prev: pointer, correct: false, next: array })
    expect(text).toBe('‘포인터’는 다시 볼 개념으로 표시했어요. 그 바탕이 되는 ‘배열’을 확인할게요.')
  })

  it('틀렸지만 다음이 바탕 개념이 아니면 이어서 확인한다고만 한다', () => {
    const text = diagnosisReason({ prev: pointer, correct: false, next: recursion })
    expect(text).toBe('‘포인터’는 다시 볼 개념으로 표시했어요. 이어서 ‘재귀’를 확인할게요.')
  })

  it('안내 상자 색은 첫 문제 중립, 맞힘 파랑, 틀림 주황', () => {
    expect(reasonTone(null)).toBe('neutral')
    expect(reasonTone(true)).toBe('known')
    expect(reasonTone(false)).toBe('gap')
  })

  it('진단이 끝났으면 문구가 없다', () => {
    expect(diagnosisReason({ prev: pointer, correct: true, next: null })).toBeNull()
  })
})
