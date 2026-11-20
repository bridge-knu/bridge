import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
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
  return (
    <div
      className="concept-node-body"
      title={data.blockId ? '눌러서 학습 블록으로 이동' : '아직 연결된 학습 블록이 없어요'}
    >
      <Handle type="target" position={Position.Top} isConnectable={false} />
      <strong>{data.label}</strong>
      <span>
        {percent}%{data.blockId ? '' : ' · 블록 준비 중'}
      </span>
      <Handle type="source" position={Position.Bottom} isConnectable={false} />
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

  const handleNodeClick = useCallback<NodeMouseHandler<ConceptNode>>(
    (_, node) => {
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
          <span className="swatch strong" /> 아는 개념 (60% 이상)
        </li>
        <li>
          <span className="swatch weak" /> 보충할 개념 (60% 미만)
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
          fitView
        >
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </section>
  )
}
