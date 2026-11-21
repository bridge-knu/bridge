// 개념 → 학습 블록 연결. GET /diagnosis/result에는 블록 ID가 없어서 content/blocks.json에서 찾는다.
// JSON은 빌드할 때 번들에 들어가므로 실행 환경에 content 폴더가 없어도 된다.
import rawBlocks from '../../../content/blocks.json'

interface BlockRef {
  id: string
  concept: string
}

const blocks: BlockRef[] = rawBlocks

// 한 개념에 블록이 여러 개면 blocks.json에서 가장 앞에 있는 블록(첫 학습 블록)으로 보낸다.
const firstBlockByConcept = new Map<string, string>()
for (const block of blocks) {
  if (!firstBlockByConcept.has(block.concept)) firstBlockByConcept.set(block.concept, block.id)
}

/** 개념의 첫 학습 블록 ID. 연결된 블록이 없으면 null */
export function findBlockId(conceptId: string): string | null {
  return firstBlockByConcept.get(conceptId) ?? null
}
