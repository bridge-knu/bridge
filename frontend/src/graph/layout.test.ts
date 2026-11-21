import { describe, expect, it } from 'vitest'
import type { ConceptResult } from '../api.ts'
import { MASTERY_THRESHOLD, buildConceptGraph, isWeak } from './layout.ts'

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
