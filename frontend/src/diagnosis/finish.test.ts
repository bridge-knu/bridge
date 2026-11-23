import { describe, expect, it } from 'vitest'
import { finishReason, progressLabel } from './finish.ts'

describe('progressLabel', () => {
  it('최대 문제 수라는 걸 드러낸다', () => {
    expect(progressLabel(3, 10)).toBe('3번째 문제 · 최대 10문제')
  })
})

describe('finishReason', () => {
  it('맞힌 문제가 있어 일찍 끝나면 건너뛰었다고 알려 준다', () => {
    expect(finishReason({ answered: 3, max: 10, correct: 3 })).toBe(
      '3문제로 일찍 끝났어요. 맞힌 개념의 바탕 개념은 안다고 보고 건너뛰어서, 더 물어볼 개념이 남지 않았어요.',
    )
  })

  it('다 틀려서 일찍 끝나면 바탕 개념까지 확인했다고 알려 준다', () => {
    expect(finishReason({ answered: 6, max: 10, correct: 0 })).toBe(
      '6문제로 일찍 끝났어요. 바탕 개념까지 차례로 확인해서, 더 물어볼 개념이 남지 않았어요.',
    )
  })

  it('최대 문제 수를 다 풀면 나머지는 추정했다고 알려 준다', () => {
    expect(finishReason({ answered: 10, max: 10, correct: 4 })).toContain('최대 10문제를 모두 풀었어요')
  })

  it('물어볼 문제 없이 끝난 경우', () => {
    expect(finishReason({ answered: 0, max: 10, correct: 0 })).toContain('물어볼 문제 없이 끝났어요')
  })
})
