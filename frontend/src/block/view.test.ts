import { describe, expect, it } from 'vitest'
import { ApiError } from '../api.ts'
import { classifyBlockError, editorLanguage, errorText, initialCode, toCheckAnswers } from './view.ts'

const practice = { lang: 'c' as const, starter: '#include <stdio.h>\n', expected: '15\n' }

describe('initialCode: 에디터 초기 코드', () => {
  it('저장된 코드가 없으면 starter', () => {
    expect(initialCode({ savedCode: null, practice })).toBe(practice.starter)
  })

  it('저장된 코드가 있으면 그것 (새로고침 후에도 서버 코드를 이어서)', () => {
    expect(initialCode({ savedCode: 'int main(){}', practice })).toBe('int main(){}')
    expect(initialCode({ savedCode: '', practice })).toBe('')
  })
})

describe('editorLanguage', () => {
  it('practice.lang을 Monaco 언어 id로', () => {
    expect(editorLanguage('c')).toBe('c')
    expect(editorLanguage('python')).toBe('python')
  })
})

describe('classifyBlockError: 블록 조회 실패', () => {
  it('401 → unauthorized', () => {
    expect(classifyBlockError(new ApiError(401, { detail: 'x', code: 'UNAUTHORIZED' }))).toBe('unauthorized')
    expect(classifyBlockError(new ApiError(401, { detail: 'x' }))).toBe('unauthorized')
  })

  it('404 → notFound (code 있든 없든)', () => {
    expect(classifyBlockError(new ApiError(404, { detail: '블록을 찾을 수 없어요', code: 'BLOCK_NOT_FOUND' }))).toBe(
      'notFound',
    )
    expect(classifyBlockError(new ApiError(404, { detail: '블록을 찾을 수 없어요' }))).toBe('notFound')
  })

  it('5xx·네트워크 → other', () => {
    expect(classifyBlockError(new ApiError(503, { detail: 'x', code: 'SERVICE_UNAVAILABLE' }))).toBe('other')
    expect(classifyBlockError(new TypeError('Failed to fetch'))).toBe('other')
  })

  it('errorText', () => {
    expect(errorText(new ApiError(404, { detail: '블록을 찾을 수 없어요' }), 'f')).toBe('블록을 찾을 수 없어요')
    expect(errorText(new ApiError(500, 'Internal Server Error'), 'f')).toBe('잠시 후 다시 시도해 주세요')
    expect(errorText(new TypeError('x'), 'f')).toContain('서버에 연결할 수 없어요')
    expect(errorText(new Error('x'), 'f')).toBe('f')
  })
})

describe('toCheckAnswers: 확인 문제 답', () => {
  it('화면 순서대로, 답하지 않은 문제는 뺀다', () => {
    expect(toCheckAnswers(['q-a', 'q-b', 'q-c'], { 'q-c': 0, 'q-a': 2 })).toEqual([
      { questionId: 'q-a', choice: 2 },
      { questionId: 'q-c', choice: 0 },
    ])
    expect(toCheckAnswers(['q-a'], {})).toEqual([])
  })
})
