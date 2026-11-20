# bridge
학업 공백 학생을 위한 선수 개념 진단·학습 계획 서비스

## 실행 방법

필요한 것: [Docker Desktop](https://www.docker.com/products/docker-desktop/) (실행 중이어야 함)

```bash
git clone https://github.com/bridge-knu/bridge.git
cd bridge
cp .env.example .env
# 로그인 토큰 서명 키를 만들어 .env의 JWT_SECRET= 뒤에 넣기 (없으면 backend가 시작하지 않음)
python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up -d
```

- http://localhost:8000/health 에서 `{"status":"ok"}` 응답이 오면 성공
- http://localhost:8000/docs 에서 API 문서 확인

종료: `docker compose down` (DB 데이터까지 지우려면 `docker compose down -v`)

로그 확인: `docker compose logs -f backend`

## 구성

| 서비스 | 포트 | 설명 |
| --- | --- | --- |
| backend | 8000 | FastAPI |
| db | 5432 | PostgreSQL 16 |
| redis | 6379 | Redis 7 |

## 폴더 구조

```
backend/        FastAPI 서버
  app/api/      API 라우터
  app/models/   DB 모델
  app/engine/   진단·플랜 엔진 (순수 함수)
  tests/        pytest
content/        개념 지도·문제·블록 JSON
frontend/       React + TypeScript (Vite)
sandbox/        코드 실행 샌드박스
deploy/         배포 설정
docs/           개발 문서
```

## API 목록

요청·응답 JSON 필드는 camelCase입니다. 필드별 모양은 http://localhost:8000/docs 에서 확인하세요.

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | /health | 서버 상태 확인 |
| POST | /auth/login | 아이디 + PIN → 토큰 (없는 아이디면 가입) |
| PUT | /profile | 이수 과목·공백·복학일·하루 시간 저장 |
| POST | /diagnosis/start | 진단 시작, 첫 문제 반환 |
| POST | /diagnosis/answer | 답 제출 → 다음 문제 또는 종료 |
| GET | /diagnosis/result | 개념별 mastery (그래프용) |
| POST | /plan/generate | 역산 플랜 생성 |
| GET | /plan | 날짜별 블록 목록, 오늘 남은 시간 |
| GET | /blocks/{id} | 강의 링크·실습·확인 문제, 저장된 코드 |
| PUT | /code/{blockId} | 코드 자동 저장 |
| POST | /run | 코드 실행 요청 → jobId |
| GET | /run/{jobId} | 실행 결과 (출력, 에러, 시간 초과) |
| POST | /blocks/{id}/complete | 블록 완료 처리 |

### 오류 응답

오류는 `{"detail": "안내 문구", "code": "오류 코드"}` 형태입니다. 화면은 `code`로 분기하고 `detail`은 그대로 보여 주면 됩니다.

| code | 상태 | detail | 언제 |
| --- | --- | --- | --- |
| UNAUTHORIZED | 401 | 다시 로그인해 주세요 | 토큰이 없거나 만료(12시간)·위조 |
| WRONG_PIN | 401 | 아이디 또는 PIN이 틀렸어요 | 로그인 PIN 틀림 |
| LOGIN_LOCKED | 429 | 1분 후 다시 시도해 주세요 | 같은 아이디로 PIN 5번 틀림 |
| DIAGNOSIS_FINISHED | 400 | 진단이 이미 끝났어요 | 끝난 진단에 답 제출 |
| QUESTION_MISMATCH | 400 | 지금 풀고 있는 문제가 아니에요 | 현재 문제가 아닌 questionId로 답 제출 |
| DIAGNOSIS_NOT_FINISHED | 400 | 진단을 먼저 끝내 주세요 | 진단을 시작하지 않았거나 끝내기 전에 결과 요청 |
| BLOCK_NOT_FOUND | 404 | 블록을 찾을 수 없어요 | 없는 블록 |
| JOB_NOT_FOUND | 404 | 실행 작업을 찾을 수 없어요 | 없거나 다른 사용자의 실행 작업 |
| SERVICE_UNAVAILABLE | 503 | 잠시 후 다시 시도해 주세요 | DB·Redis에 연결할 수 없음 |

입력값이 형식에 맞지 않으면 422이고, FastAPI 기본 형태(`{"detail": [...]}`, `code` 없음)입니다.

### 로그인

- 아이디 + 숫자 4자리 PIN. 없는 아이디로 로그인하면 그 PIN으로 가입됩니다 (`isNewUser: true`).
- **데모 계정: `demo` / `0000`** (서버가 시작할 때 자동으로 만들어짐)
- 같은 아이디로 PIN을 5번 틀리면 1분 동안 로그인이 막힙니다 (429).
- 로그인 외의 모든 API는 `Authorization: Bearer <token>` 헤더가 필요합니다. 토큰이 없거나 만료(12시간)·위조면 401 `UNAUTHORIZED`.
- http://localhost:8000/docs 에서 시험할 때는 `/auth/login`으로 받은 `token`을 오른쪽 위 **Authorize** 버튼에 넣으세요 (`Bearer` 없이 토큰만).

### 아직 mock인 API

로그인을 뺀 나머지는 DB와 엔진이 연결되기 전까지 가짜 데이터를 돌려줍니다. 저장한 값은 서버를 재시작하면 사라집니다. 화면에서 오류 상황을 확인할 때 아래 값을 쓰세요.

| 상황 | 방법 |
| --- | --- |
| 코드 실행 시간 초과 | 코드에 `while (1)` 또는 `for (;;)` |
| 컴파일 에러 | 코드에 `COMPILE_ERROR` |

코드 실행은 1초 동안 `running`이었다가 `done`이 됩니다.

## DB

테이블은 `backend/app/models/`에 있고, backend 컨테이너가 시작할 때 마이그레이션(`alembic upgrade head`)이 자동으로 적용됩니다.

모델을 바꿨다면 마이그레이션 파일을 만들어서 같이 커밋하세요.

```bash
docker compose exec backend alembic revision --autogenerate -m "변경 내용"
docker compose exec backend alembic upgrade head
```

DB를 처음 상태로 되돌리려면 `docker compose down -v` 후 다시 `docker compose up -d` 하세요.

## 테스트

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

API·DB 테스트는 `docker compose up -d`로 postgres가 떠 있을 때만 실행되고, 없으면 건너뜁니다. PR을 올리기 전에는 `REQUIRE_DB=1 pytest`로 돌려서 건너뛴 테스트 없이 모두 통과하는지 확인하세요. Redis는 테스트용 가짜(fakeredis)를 씁니다. 테스트 데이터는 끝나면 되돌려서 DB에 남지 않습니다.

개발 규칙은 [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)를 참고하세요.
