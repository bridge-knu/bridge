import { useParams } from 'react-router-dom'

export default function BlockPage() {
  const { blockId } = useParams()

  return (
    <section>
      <h1>블록 학습</h1>
      <p>블록 ID: {blockId}</p>
      <p className="placeholder">강의 영상, 실습 코드 실행, 확인 문제를 한 화면에서 진행합니다. (C6에서 구현)</p>
    </section>
  )
}
