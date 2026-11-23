// GET /diagnosis/result의 개념 목록을 React Flow 노드·간선으로 바꾸고 dagre로 배치한다.
import dagre from '@dagrejs/dagre'
import { MarkerType, Position, type Edge, type Node } from '@xyflow/react'
import type { ConceptResult } from '../api.ts'

/** 이 값 미만이면 보충이 필요한 개념(주황·!), 이상이면 아는 개념(파랑·✓) */
export const MASTERY_THRESHOLD = 0.6

const NODE_WIDTH = 160
const NODE_HEIGHT = 56

export interface ConceptNodeData extends Record<string, unknown> {
  label: string
  concept: ConceptResult
  weak: boolean
  /** 연결된 학습 블록. 없으면 null (클릭 불가) */
  blockId: string | null
}

export type ConceptNode = Node<ConceptNodeData>

export function isWeak(mastery: number): boolean {
  return mastery < MASTERY_THRESHOLD
}

export function buildConceptGraph(
  concepts: ConceptResult[],
  findBlockId: (conceptId: string) => string | null,
): { nodes: ConceptNode[]; edges: Edge[] } {
  const ids = new Set(concepts.map((c) => c.id))

  // 선수 개념 → 목표 개념. 결과에 없는 선수 개념은 간선을 만들지 않는다.
  const edges: Edge[] = concepts.flatMap((c) =>
    c.prereqs
      .filter((p) => ids.has(p))
      .map((p) => ({
        id: `${p}->${c.id}`,
        source: p,
        target: c.id,
        markerEnd: { type: MarkerType.ArrowClosed },
      })),
  )

  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'TB', nodesep: 40, ranksep: 70 })
  g.setDefaultEdgeLabel(() => ({}))
  for (const c of concepts) g.setNode(c.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  for (const e of edges) g.setEdge(e.source, e.target)
  dagre.layout(g)

  const nodes: ConceptNode[] = concepts.map((c) => {
    const { x, y } = g.node(c.id)
    const weak = isWeak(c.mastery)
    const blockId = findBlockId(c.id)
    return {
      id: c.id,
      type: 'concept',
      // dagre는 중심 좌표, React Flow는 왼쪽 위 좌표
      position: { x: x - NODE_WIDTH / 2, y: y - NODE_HEIGHT / 2 },
      data: { label: c.name, concept: c, weak, blockId },
      className: `concept-node ${weak ? 'weak' : 'strong'}${blockId ? ' clickable' : ''}`,
      style: { width: NODE_WIDTH, height: NODE_HEIGHT },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      connectable: false,
    }
  })

  return { nodes, edges }
}
