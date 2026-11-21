// 유튜브 강의를 iframe으로 임베드할 주소를 만든다. 영상은 링크·임베드로만 쓴다 (다운로드·복사 없음).

import type { BlockVideo } from '../api.ts'

const ID_PATTERN = /^[A-Za-z0-9_-]{6,}$/

/** youtube.com/watch?v=, youtu.be/, youtube.com/embed/ 주소에서 영상 id를 꺼낸다. 아니면 null */
export function youtubeId(url: string): string | null {
  let u: URL
  try {
    u = new URL(url)
  } catch {
    return null
  }
  if (u.protocol !== 'https:' && u.protocol !== 'http:') return null
  const host = u.hostname.replace(/^www\.|^m\./, '')
  let id: string | null = null
  if (host === 'youtube.com') {
    if (u.pathname === '/watch') id = u.searchParams.get('v')
    else if (u.pathname.startsWith('/embed/')) id = u.pathname.slice('/embed/'.length)
  } else if (host === 'youtu.be') {
    id = u.pathname.slice(1)
  }
  return id && ID_PATTERN.test(id) ? id : null
}

/**
 * 임베드 주소. start·end(초)를 붙인다.
 * start가 음수·소수면 정수로 맞추고, end가 start보다 크지 않으면 end는 빼서 영상 끝까지 재생한다.
 * 영상 주소가 유튜브가 아니면 null.
 */
export function embedUrl(video: BlockVideo | null | undefined): string | null {
  if (!video) return null
  const id = youtubeId(video.url)
  if (!id) return null
  const start = Number.isFinite(video.start) ? Math.max(0, Math.floor(video.start)) : 0
  const end = Number.isFinite(video.end) ? Math.floor(video.end) : 0
  const params = new URLSearchParams({ rel: '0' })
  if (start > 0) params.set('start', String(start))
  if (end > start) params.set('end', String(end))
  return `https://www.youtube.com/embed/${id}?${params.toString()}`
}

/** 125 → "2:05" */
export function formatSeconds(total: number): string {
  const s = Math.max(0, Math.floor(total))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = String(s % 60).padStart(2, '0')
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`
}
