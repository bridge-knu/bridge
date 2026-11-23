// GET /diagnosis/result의 개념 목록을 React Flow 노드·간선으로 바꾸고 dagre로 배치한다.
import dagre from '@dagrejs/dagre'
import { MarkerType, Position, type Edge, type Node } from '@xyflow/react'
import type { ConceptResult } from '../api.ts'

/** 이 값 미만이면 보충이 필요한 개념(주황·!), 이상이면 아는 개념(파랑·✓) */
export const MASTERY_THRESHOLD = 0.6

export const NODE_WIDTH = 160
export const NODE_HEIGHT = 56

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

/** 노드 글자(14px)가 화면에서 12px 넘게 보이는 배율. 전체가 이보다 작아져야 들어가면 한 화면에 맞추지 않는다 */
export const READABLE_ZOOM = 0.9
/** 전체를 한 화면에 맞췄을 때 이 배율 이상이면 그대로 전체를 보여 준다 */
export const FIT_MIN_ZOOM = 0.85
const FIT_MAX_ZOOM = 1.2
const FIT_PADDING = 0.1

export interface GraphViewport {
  x: number
  y: number
  zoom: number
  /** 그래프 전체가 화면 안에 들어왔는지 (false면 끌어서 나머지를 봐야 함) */
  whole: boolean
}

function bounds(nodes: Pick<ConceptNode, 'position'>[]) {
  const minX = Math.min(...nodes.map((n) => n.position.x))
  const maxX = Math.max(...nodes.map((n) => n.position.x + NODE_WIDTH))
  const minY = Math.min(...nodes.map((n) => n.position.y))
  const maxY = Math.max(...nodes.map((n) => n.position.y + NODE_HEIGHT))
  return { minX, minY, width: maxX - minX, height: maxY - minY }
}

/**
 * 그래프를 처음 열 때의 화면 위치.
 * 전체를 맞춰도 읽을 수 있으면 가운데에 전체를 놓고, 아니면 READABLE_ZOOM으로
 * 그래프 맨 위(기초 개념)를 가로 가운데에 놓는다. 나머지는 끌어서(휴대폰은 손가락으로 밀어서) 본다.
 */
export function initialViewport(
  nodes: Pick<ConceptNode, 'position'>[],
  containerWidth: number,
  containerHeight: number,
  paddingTop = 24,
): GraphViewport {
  if (nodes.length === 0) return { x: 0, y: 0, zoom: 1, whole: true }
  const b = bounds(nodes)
  const fit = Math.min(
    containerWidth / (b.width * (1 + 2 * FIT_PADDING)),
    containerHeight / (b.height * (1 + 2 * FIT_PADDING)),
    FIT_MAX_ZOOM,
  )
  if (fit >= FIT_MIN_ZOOM) {
    return {
      x: (containerWidth - b.width * fit) / 2 - b.minX * fit,
      y: (containerHeight - b.height * fit) / 2 - b.minY * fit,
      zoom: fit,
      whole: true,
    }
  }
  const zoom = READABLE_ZOOM
  return {
    x: (containerWidth - b.width * zoom) / 2 - b.minX * zoom,
    y: paddingTop - b.minY * zoom,
    zoom,
    whole: false,
  }
}
