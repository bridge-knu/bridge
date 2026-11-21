import { describe, expect, it } from 'vitest'
import { embedUrl, formatSeconds, youtubeId } from './video.ts'

describe('youtubeId', () => {
  it('watch, youtu.be, embed 주소', () => {
    expect(youtubeId('https://www.youtube.com/watch?v=hxF6I0iVp_o')).toBe('hxF6I0iVp_o')
    expect(youtubeId('https://youtube.com/watch?v=hxF6I0iVp_o&t=30')).toBe('hxF6I0iVp_o')
    expect(youtubeId('https://m.youtube.com/watch?v=hxF6I0iVp_o')).toBe('hxF6I0iVp_o')
    expect(youtubeId('https://youtu.be/hxF6I0iVp_o')).toBe('hxF6I0iVp_o')
    expect(youtubeId('https://www.youtube.com/embed/hxF6I0iVp_o')).toBe('hxF6I0iVp_o')
  })

  it('유튜브가 아니거나 형식이 틀리면 null', () => {
    expect(youtubeId('')).toBeNull()
    expect(youtubeId('not a url')).toBeNull()
    expect(youtubeId('https://example.com/watch?v=hxF6I0iVp_o')).toBeNull()
    expect(youtubeId('https://www.youtube.com/watch')).toBeNull()
    expect(youtubeId('javascript:alert(1)')).toBeNull()
    expect(youtubeId('https://www.youtube.com/watch?v=<script>')).toBeNull()
  })
})

describe('embedUrl: 시작·종료 시간', () => {
  it('start·end를 초 단위로 붙인다', () => {
    expect(embedUrl({ url: 'https://www.youtube.com/watch?v=hxF6I0iVp_o', start: 30, end: 753 })).toBe(
      'https://www.youtube.com/embed/hxF6I0iVp_o?rel=0&start=30&end=753',
    )
  })

  it('start가 0이면 start는 빼고 end만', () => {
    expect(embedUrl({ url: 'https://www.youtube.com/watch?v=jNQXAC9IVRw', start: 0, end: 600 })).toBe(
      'https://www.youtube.com/embed/jNQXAC9IVRw?rel=0&end=600',
    )
  })

  it('end가 start보다 크지 않으면 end는 빼고 영상 끝까지', () => {
    expect(embedUrl({ url: 'https://youtu.be/jNQXAC9IVRw', start: 100, end: 100 })).toBe(
      'https://www.youtube.com/embed/jNQXAC9IVRw?rel=0&start=100',
    )
    expect(embedUrl({ url: 'https://youtu.be/jNQXAC9IVRw', start: 0, end: 0 })).toBe(
      'https://www.youtube.com/embed/jNQXAC9IVRw?rel=0',
    )
  })

  it('음수·소수는 정리한다', () => {
    expect(embedUrl({ url: 'https://youtu.be/jNQXAC9IVRw', start: -5, end: 12.7 })).toBe(
      'https://www.youtube.com/embed/jNQXAC9IVRw?rel=0&end=12',
    )
  })

  it('영상이 없거나 유튜브가 아니면 null', () => {
    expect(embedUrl(null)).toBeNull()
    expect(embedUrl(undefined)).toBeNull()
    expect(embedUrl({ url: '', start: 0, end: 10 })).toBeNull()
    expect(embedUrl({ url: 'https://example.com/v.mp4', start: 0, end: 10 })).toBeNull()
  })
})

describe('formatSeconds', () => {
  it('분:초, 1시간 이상은 시:분:초', () => {
    expect(formatSeconds(0)).toBe('0:00')
    expect(formatSeconds(753)).toBe('12:33')
    expect(formatSeconds(3725)).toBe('1:02:05')
  })
})
