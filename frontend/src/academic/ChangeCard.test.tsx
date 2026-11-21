import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ChangeCard from './ChangeCard.tsx'
import type { AcademicChange } from './changes.ts'

// 테스트 전용 가짜 항목. 실제 학사 변경 내용이 아니다.
const base: AcademicChange = {
  id: 'test',
  effectiveDate: '2024-03-01',
  admissionYearFrom: null,
  admissionYearTo: null,
  title: '테스트 제목',
  summary: '테스트 요약',
  sourceUrl: 'https://example.com/notice?id=1&x=2',
}

describe('ChangeCard', () => {
  it('시행 시기·대상·제목·요약·출처 링크를 보여 준다', () => {
    const html = renderToStaticMarkup(<ChangeCard change={base} />)
    expect(html).toContain('<time dateTime="2024-03-01">2024년 3월 1일 시행</time>')
    expect(html).toContain('전체 학번 대상')
    expect(html).toContain('테스트 제목')
    expect(html).toContain('테스트 요약')
  })

  it('출처 링크는 새 탭 + noopener noreferrer', () => {
    const html = renderToStaticMarkup(<ChangeCard change={base} />)
    expect(html).toContain('href="https://example.com/notice?id=1&amp;x=2"')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noopener noreferrer"')
  })

  it('특정 학번 대상 항목은 강조 표시', () => {
    const html = renderToStaticMarkup(<ChangeCard change={{ ...base, admissionYearFrom: 2020, admissionYearTo: 2022 }} />)
    expect(html).toContain('academic-change mine')
    expect(html).toContain('내 학번 대상 · 2020~2022학번')
  })
})
