import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type NodeMouseHandler,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { getDiagnosisResult, setAuthToken, type ConceptResult } from '../api.ts'
import { findBlockId } from '../graph/blocks.ts'
import { classifyResultError, resultErrorMessage } from '../graph/errors.ts'
import { buildConceptGraph, type ConceptNode } from '../graph/layout.ts'

type State =
  | { status: 'loading' }
  | { status: 'notFinished' }
  | { status: 'error'; message: string }
  | { status: 'ready'; concepts: ConceptResult[] }

function ConceptNodeView({ data }: NodeProps<ConceptNode>) {
  const percent = Math.round(data.concept.mastery * 100)
  const content = (
    <>
      <Handle type="target" position={Position.Top} isConnectable={false} />
      <strong>
        <span className="concept-icon" aria-hidden="true">
          {data.weak ? '!' : '✓'}
        </span>
        {data.label}
      </strong>
      <span>
        <span className="visually-hidden">{data.weak ? '보충할 개념, ' : '아는 개념, '}</span>
        {percent}%{data.blockId ? '' : ' · 블록 준비 중'}
      </span>
      <Handle type="source" position={Position.Bottom} isConnectable={false} />
    </>
  )

  // 블록이 있는 개념은 진짜 링크로 만들어 마우스·키보드(Tab, Enter) 모두 블록으로 이동하게 한다
  if (data.blockId) {
    return (
      <Link
        to={`/blocks/${encodeURIComponent(data.blockId)}`}
        className="concept-node-body concept-link"
        title="눌러서 학습 블록으로 이동"
      >
        {content}
      </Link>
    )
  }
  return (
    <div className="concept-node-body" title="아직 연결된 학습 블록이 없어요">
      {content}
    </div>
  )
}

// 렌더마다 새 객체를 만들면 React Flow가 노드를 다시 만들므로 컴포넌트 밖에 둔다.
const nodeTypes = { concept: ConceptNodeView }

export default function ResultPage() {
  const navigate = useNavigate()
  const [state, setState] = useState<State>({ status: 'loading' })
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading' })
    getDiagnosisResult()
      .then((res) => {
        if (!cancelled) setState({ status: 'ready', concepts: res.concepts })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const kind = classifyResultError(err)
        // 토큰이 없거나 만료됨 (새로고침하면 메모리 토큰이 사라짐) → 다시 로그인
        if (kind === 'unauthorized') {
          setAuthToken(null)
          navigate('/login', { replace: true })
          return
        }
        if (kind === 'notFinished') {
          setState({ status: 'notFinished' })
          return
        }
        setState({ status: 'error', message: resultErrorMessage(err) })
      })
    return () => {
      cancelled = true
    }
  }, [navigate, reloadKey])

  const graph = useMemo(() => {
    if (state.status !== 'ready') return null
    return buildConceptGraph(state.concepts, findBlockId)
  }, [state])

  // React Flow는 클릭 처리기가 없으면 노드의 마우스 이벤트를 꺼 버린다 (pointer-events: none).
  // 노드 안 링크가 이미 이동했으면(defaultPrevented) 건너뛰고, 링크 바깥 테두리를 눌렀을 때만 여기서 이동한다.
  const handleNodeClick = useCallback<NodeMouseHandler<ConceptNode>>(
    (event, node) => {
      if (event.defaultPrevented) return
      const { blockId } = node.data
      if (blockId) navigate(`/blocks/${encodeURIComponent(blockId)}`)
    },
    [navigate],
  )

  if (state.status === 'loading') {
    return (
      <section>
        <h1>진단 결과</h1>
        <p className="form-hint" role="status">
          결과를 불러오는 중…
        </p>
      </section>
    )
  }

  if (state.status === 'error') {
    return (
      <section className="form-page">
        <h1>진단 결과</h1>
        <p className="form-error" role="alert">
          {state.message}
        </p>
        <div className="form">
          <button type="button" onClick={() => setReloadKey((k) => k + 1)}>
            다시 불러오기
          </button>
        </div>
      </section>
    )
  }

  // 진단을 끝내지 않았거나(400 DIAGNOSIS_NOT_FINISHED) 결과에 개념이 하나도 없음
  if (state.status === 'notFinished' || !graph || graph.nodes.length === 0) {
    return (
      <section className="form-page">
        <h1>진단 결과</h1>
        <p className="form-hint">
          {state.status === 'notFinished'
            ? '진단을 먼저 끝내 주세요.'
            : '아직 진단 결과가 없어요. 진단을 먼저 진행해 주세요.'}
        </p>
        <div className="form">
          <button type="button" onClick={() => navigate('/diagnosis')}>
            진단하러 가기
          </button>
        </div>
      </section>
    )
  }

  const weakCount = graph.nodes.filter((n) => n.data.weak).length

  return (
    <section>
      <h1>진단 결과</h1>
      <p className="form-hint">
        개념 {graph.nodes.length}개 중 {weakCount}개를 보충하면 돼요. 위에서 아래로 선수 개념 → 목표 개념 순서예요.
        노드를 누르면 학습 블록으로 이동해요.
      </p>
      <ul className="concept-legend">
        <li>
          <span className="swatch strong" aria-hidden="true">
            ✓
          </span> 아는 개념 (60% 이상)
        </li>
        <li>
          <span className="swatch weak" aria-hidden="true">
            !
          </span> 보충할 개념 (60% 미만)
        </li>
      </ul>
      <div className="concept-graph">
        <ReactFlow
          nodes={graph.nodes}
          edges={graph.edges}
          nodeTypes={nodeTypes}
          onNodeClick={handleNodeClick}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          // 노드 안의 링크가 포커스를 받으므로 노드·간선 자체는 Tab 순서에서 뺀다
          nodesFocusable={false}
          edgesFocusable={false}
          // 개념 20개 안팎이면 그래프가 화면보다 훨씬 길다. 기본 최소 배율(0.5)에서는 다 못 넣어서
          // 맨 위(기초 개념)가 잘리므로 더 작게 줄일 수 있게 하고, 처음 열 때 전체가 보이게 맞춘다
          minZoom={0.1}
          fitView
          fitViewOptions={{ padding: 0.1 }}
        >
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </section>
  )
}
