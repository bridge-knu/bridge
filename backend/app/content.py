"""content/*.json을 한 번만 읽어 개념 그래프로 들고 있는다.

콘텐츠는 DB에 넣지 않는다. 서버가 시작할 때 읽고, 형식이 틀리면 서버가 뜨지 않는다.
CONTENT_DIR이 없으면 저장소의 content/ 폴더를 쓴다 (로컬 테스트용).
"""

import os
from functools import lru_cache
from pathlib import Path

from app.engine.graph import Graph, load_graph

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "content"


@lru_cache(maxsize=1)
def get_graph() -> Graph:
    return load_graph(os.environ.get("CONTENT_DIR") or DEFAULT_DIR)


def concept_of_block(graph: Graph, block_id: str) -> str | None:
    """블록의 개념 id. blocks.json에 없는 블록은 엔진 규칙(b-{개념}-{번호})으로 읽는다."""
    block = graph.blocks.get(block_id)
    if block is not None:
        return block.concept
    if block_id.startswith("b-") and "-" in block_id[2:]:
        concept_id = block_id[2:].rsplit("-", 1)[0]
        if concept_id in graph.concepts:
            return concept_id
    return None
