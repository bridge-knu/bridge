import { describe, expect, it } from 'vitest'
import type { ConceptResult } from '../api.ts'
import {
  FIT_MIN_ZOOM,
  MASTERY_THRESHOLD,
  NODE_HEIGHT,
  NODE_WIDTH,
  READABLE_ZOOM,
  buildConceptGraph,
  initialViewport,
  isWeak,
} from './layout.ts'

const concept = (id: string, prereqs: string[], mastery: number): ConceptResult => ({
  id,
  name: id.toUpperCase(),
  course: 'C',
  prereqs,
  mastery,
  source: 'diagnosed',
})

// mock API(GET /diagnosis/result)와 같은 모양: 배열 → 포인터 → 연결 리스트
const sample = [
  concept('array', [], 0.85),
  concept('pointer', ['array'], 0.4),
  concept('linked_list', ['pointer'], 0.6),
]

const noBlock = () => null

describe('isWeak', () => {
  it('0.6 미만은 보충 필요, 0.6 이상은 아는 개념', () => {
    expect(MASTERY_THRESHOLD).toBe(0.6)
    expect(isWeak(0.59)).toBe(true)
    expect(isWeak(0.6)).toBe(false)
    expect(isWeak(1)).toBe(false)
    expect(isWeak(0)).toBe(true)
  })
})

describe('buildConceptGraph', () => {
  it('선수 개념 → 후속 개념 방향으로 간선을 만든다', () => {
    const { edges } = buildConceptGraph(sample, noBlock)
    expect(edges.map((e) => [e.source, e.target])).toEqual([
      ['array', 'pointer'],
      ['pointer', 'linked_list'],
    ])
  })

  it('결과에 없는 선수 개념으로는 간선을 만들지 않는다', () => {
    const { nodes, edges } = buildConceptGraph([concept('pointer', ['array', 'function'], 0.5)], noBlock)
    expect(nodes).toHaveLength(1)
    expect(edges).toEqual([])
  })

  it('숙련도로 노드 색(weak/strong)을 정한다', () => {
    const { nodes } = buildConceptGraph(sample, noBlock)
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]))
    expect(byId.array.data.weak).toBe(false)
    expect(byId.array.className).toContain('strong')
    expect(byId.pointer.data.weak).toBe(true)
    expect(byId.pointer.className).toContain('weak')
    expect(byId.linked_list.data.weak).toBe(false)
  })

  it('dagre 배치에서 선수 개념이 후속 개념보다 위에 온다', () => {
    const { nodes } = buildConceptGraph(sample, noBlock)
    const y = Object.fromEntries(nodes.map((n) => [n.id, n.position.y]))
    expect(y.array).toBeLessThan(y.pointer)
    expect(y.pointer).toBeLessThan(y.linked_list)
  })

  it('블록이 있는 개념만 클릭할 수 있다', () => {
    const { nodes } = buildConceptGraph(sample, (id) => (id === 'array' ? 'b-array-1' : null))
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]))
    expect(byId.array.data.blockId).toBe('b-array-1')
    expect(byId.array.className).toContain('clickable')
    expect(byId.pointer.data.blockId).toBeNull()
    expect(byId.pointer.className).not.toContain('clickable')
  })

  it('빈 결과는 빈 그래프', () => {
    expect(buildConceptGraph([], noBlock)).toEqual({ nodes: [], edges: [] })
  })
})

describe('initialViewport (그래프 첫 화면)', () => {
  const at = (x: number, y: number) => ({ position: { x, y } })

  it('작은 그래프는 전체를 가운데에 맞춘다', () => {
    // 그래프 크기 160 x 56, 화면 900 x 900 → 최대 배율 1.2로 가운데
    const v = initialViewport([at(0, 0)], 900, 900)
    expect(v.whole).toBe(true)
    expect(v.zoom).toBe(1.2)
    expect(v.x).toBeCloseTo((900 - NODE_WIDTH * 1.2) / 2)
    expect(v.y).toBeCloseTo((900 - NODE_HEIGHT * 1.2) / 2)
  })

  it('맞추면 글자가 작아지는 큰 그래프는 읽을 수 있는 배율로 맨 위 가운데부터 보여 준다', () => {
    // 폭 1700, 높이 1800인 그래프를 358 x 640 화면에
    const nodes = [at(0, 100), at(1700 - NODE_WIDTH, 100 + 1800 - NODE_HEIGHT)]
    const v = initialViewport(nodes, 358, 640, 24)
    expect(v.whole).toBe(false)
    expect(v.zoom).toBe(READABLE_ZOOM)
    expect(v.y).toBeCloseTo(24 - 100 * READABLE_ZOOM)
    // 양옆이 같은 만큼 잘려서 맨 위 가운데 노드가 보인다
    const left = 0 * v.zoom + v.x
    const right = 1700 * v.zoom + v.x
    expect(left).toBeCloseTo(358 - right)
  })

  it('전체를 맞춘 배율이 기준 이상이면 전체 보기', () => {
    // 높이 기준 배율이 FIT_MIN_ZOOM 바로 위가 되도록
    const h = 1000 / (1.2 * FIT_MIN_ZOOM) - 1
    const v = initialViewport([at(0, 0), at(0, h - NODE_HEIGHT)], 2000, 1000)
    expect(v.whole).toBe(true)
    expect(v.zoom).toBeGreaterThanOrEqual(FIT_MIN_ZOOM)
  })

  it('노드가 없으면 원점', () => {
    expect(initialViewport([], 300, 300)).toEqual({ x: 0, y: 0, zoom: 1, whole: true })
  })
})
