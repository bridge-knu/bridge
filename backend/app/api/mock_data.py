"""mock API용 가짜 데이터와 메모리 저장소.

content/ 샘플(배열 → 포인터 → 연결 리스트)과 같은 내용을 쓴다.
DB(A2)와 엔진(A7)이 연결되면 이 파일은 지운다.
서버를 재시작하면 저장된 값은 모두 사라진다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import Depends

from app.api.deps import get_current_user
from app.models import User

CONCEPTS = [
    {"id": "array", "name": "배열", "course": "C", "prereqs": []},
    {"id": "pointer", "name": "포인터", "course": "C", "prereqs": ["array"]},
    {"id": "linked_list", "name": "연결 리스트", "course": "DS", "prereqs": ["pointer"]},
]
CONCEPT_NAME = {c["id"]: c["name"] for c in CONCEPTS}

QUESTIONS = [
    {
        "id": "q-array-1",
        "concept": "array",
        "prompt": "아래 코드에서 a[3]의 값은?",
        "code": "int a[5] = {1, 2, 3};",
        "choices": ["0", "3", "쓰레기 값", "컴파일 에러"],
        "answer": 0,
    },
    {
        "id": "q-array-2",
        "concept": "array",
        "prompt": "아래 코드에서 sizeof(a) / sizeof(a[0])의 값은?",
        "code": "int a[4];",
        "choices": ["1", "4", "16", "int 크기에 따라 다르다"],
        "answer": 1,
    },
    {
        "id": "q-pointer-1",
        "concept": "pointer",
        "prompt": "아래 코드를 실행한 뒤 a의 값은?",
        "code": "int a = 3;\nint *p = &a;\n*p = 5;",
        "choices": ["3", "5", "a의 주소값", "컴파일 에러"],
        "answer": 1,
    },
    {
        "id": "q-pointer-2",
        "concept": "pointer",
        "prompt": "아래 코드를 실행한 뒤 *p의 값은?",
        "code": "int a[3] = {10, 20, 30};\nint *p = a;\np++;",
        "choices": ["10", "20", "30", "a의 주소 + 1"],
        "answer": 1,
    },
    {
        "id": "q-linked_list-1",
        "concept": "linked_list",
        "prompt": "단일 연결 리스트의 맨 앞(head 앞)에 새 노드를 삽입하는 연산의 시간 복잡도는?",
        "code": None,
        "choices": ["O(1)", "O(log n)", "O(n)", "O(n log n)"],
        "answer": 0,
    },
    {
        "id": "q-linked_list-2",
        "concept": "linked_list",
        "prompt": "아래 구조체로 만든 단일 연결 리스트에서 마지막 노드의 next에 들어가는 값은?",
        "code": "struct Node {\n    int data;\n    struct Node *next;\n};",
        "choices": ["NULL", "자기 자신의 주소", "head의 주소", "0이 아닌 아무 값"],
        "answer": 0,
    },
]
QUESTION_BY_ID = {q["id"]: q for q in QUESTIONS}

# 진단은 개념마다 첫 문제 하나씩, 이 순서로 낸다.
DIAGNOSIS_ORDER = ["q-array-1", "q-pointer-1", "q-linked_list-1"]

BLOCKS = [
    {
        "id": "b-array-1",
        "concept": "array",
        "minutes": 30,
        "video": {"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw", "start": 0, "end": 600},
        "practice": {
            "lang": "c",
            "starter": "#include <stdio.h>\n\nint main(void) {\n    int a[5] = {1, 2, 3, 4, 5};\n"
            "    int sum = 0;\n\n    /* 반복문으로 a의 모든 원소를 더해 sum에 저장하세요 */\n\n"
            '    printf("%d\\n", sum);\n    return 0;\n}\n',
            "expected": "15\n",
        },
        "check": ["q-array-2"],
    },
    {
        "id": "b-pointer-1",
        "concept": "pointer",
        "minutes": 30,
        "video": {"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw", "start": 0, "end": 720},
        "practice": {
            "lang": "c",
            "starter": "#include <stdio.h>\n\nint main(void) {\n    int a = 3;\n    int *p = &a;\n\n"
            "    /* a를 직접 쓰지 말고, p를 이용해 a의 값을 5로 바꾸세요 */\n\n"
            '    printf("%d\\n", a);\n    return 0;\n}\n',
            "expected": "5\n",
        },
        "check": ["q-pointer-2"],
    },
    {
        "id": "b-linked_list-1",
        "concept": "linked_list",
        "minutes": 30,
        "video": {"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw", "start": 0, "end": 900},
        "practice": {
            "lang": "c",
            "starter": "#include <stdio.h>\n#include <stdlib.h>\n\nstruct Node {\n    int data;\n"
            "    struct Node *next;\n};\n\nint main(void) {\n"
            "    /* 1, 2, 3을 담은 연결 리스트를 만들고 순서대로 출력하세요 */\n\n    return 0;\n}\n",
            "expected": "1 2 3\n",
        },
        "check": ["q-linked_list-2"],
    },
]
BLOCK_BY_ID = {b["id"]: b for b in BLOCKS}

# 진단 결과 (mastery는 그럴듯한 고정값)
MASTERY = {
    "array": (0.85, "diagnosed"),
    "pointer": (0.4, "diagnosed"),
    "linked_list": (0.15, "prior"),
}


def now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class UserState:
    diagnosis_index: int = 0
    plan_created: bool = False
    done_blocks: set[str] = field(default_factory=set)


@dataclass
class Job:
    job_id: str
    user_id: int
    created: float
    lang: str
    code: str
    block_id: str | None


USERS: dict[int, UserState] = {}
JOBS: dict[str, Job] = {}


def current_user(user: User = Depends(get_current_user)) -> UserState:
    """로그인한 사용자의 mock 상태. 토큰이 없거나 잘못되면 get_current_user가 401을 낸다."""
    return USERS.setdefault(user.id, UserState())
