import { describe, expect, it } from 'vitest'
import rawBlocks from '../../../content/blocks.json'
import { findBlockId } from './blocks.ts'

describe('findBlockId (content/blocks.json)', () => {
  it('개념마다 blocks.json에서 처음 나오는 블록 ID를 돌려준다', () => {
    const firstByConcept = new Map<string, string>()
    for (const b of rawBlocks) if (!firstByConcept.has(b.concept)) firstByConcept.set(b.concept, b.id)
    expect(firstByConcept.size).toBeGreaterThan(0)
    for (const [concept, blockId] of firstByConcept) expect(findBlockId(concept)).toBe(blockId)
  })

  it('블록이 없는 개념은 null', () => {
    expect(findBlockId('no-such-concept')).toBeNull()
  })
})
