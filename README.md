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
| worker | - | 코드 실행 작업 처리 (샌드박스 컨테이너 실행) |

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
| SERVICE_UNAVAILABLE | 503 | 잠시 후 다시 시도해 주세요 | DB·Redis에 연결할 수 없음, 코드 실행 대기열이 가득 참 |
| TOO_MANY_REQUESTS | 429 | 요청이 너무 많아요. 잠시 후 다시 시도해 주세요 | 같은 IP에서 로그인 1분 60번 또는 새 계정 1시간 30개를 넘음, 코드 실행 1분 20번을 넘음 |

입력값이 형식에 맞지 않으면 422이고, FastAPI 기본 형태(`{"detail": [...]}`, `code` 없음)입니다.

### 로그인

- 아이디 + 숫자 4자리 PIN. 없는 아이디로 로그인하면 그 PIN으로 가입됩니다.
- `isNewUser`는 프로필을 아직 저장하지 않았으면 `true`입니다. 가입만 하고 프로필 입력 전에 나간 사용자도 다시 `true`가 됩니다.
- **데모 계정: `demo` / `0000`** (서버가 시작할 때 프로필까지 자동으로 만들어져서 바로 플랜 화면으로 갑니다)
- 같은 아이디로 PIN을 5번 틀리면 1분 동안 로그인이 막힙니다 (429).
- 같은 IP에서는 로그인 1분 60번, 새 계정 1시간 30개까지입니다 (429 `TOO_MANY_REQUESTS`). 여러 아이디를 돌아가며 PIN을 맞히거나 계정을 대량으로 만드는 것을 막습니다.
- 배포에서는 `DISABLE_DOCS=1`로 `/docs`와 `/openapi.json`을 끕니다.
- 로그인 외의 모든 API는 `Authorization: Bearer <token>` 헤더가 필요합니다. 토큰이 없거나 만료(12시간)·위조면 401 `UNAUTHORIZED`.
- http://localhost:8000/docs 에서 시험할 때는 `/auth/login`으로 받은 `token`을 오른쪽 위 **Authorize** 버튼에 넣으세요 (`Bearer` 없이 토큰만).

### 프로필·코드 자동 저장

- `PUT /profile`과 `PUT /code/{blockId}`는 DB에 저장되어 서버를 재시작해도 남습니다. 다시 저장하면 덮어씁니다 (사용자당 프로필 1개, 블록당 코드 1개).
- 저장한 코드는 `GET /blocks/{blockId}`의 `savedCode`, `savedAt`으로 돌아옵니다.
- `GET /plan`의 `dailyMinutes`, `returnDate`도 저장된 프로필을 씁니다.

### 플랜의 날짜와 남은 시간

- 날짜는 모두 **한국 시간** 기준입니다. 응답의 `today`가 서버 기준 오늘 날짜이니, 화면은 브라우저 날짜 대신 이 값을 쓰세요.
- `todayRemainingMinutes` = 하루 가용 시간 − 오늘 완료한 블록 시간 (최소 0). "이 블록까지 가능"은 안 끝낸 블록 시간을 순서대로 더해서 이 값 안에 드는 데까지입니다.

### 플랜의 미룬 개념

복학일까지 시간이 부족하면 `POST /plan/generate`, `GET /plan` 응답의 `deferredConcepts`에 복학 후로 미룬 개념(`conceptId`, `conceptName`, `blocks`)이, `message`에 안내 문구가 옵니다. 미룬 개념이 없으면 `[]`와 `null`입니다. mock에서는 프로필의 복학일을 내일, 하루 30분으로 저장하면 확인할 수 있습니다.

### 아직 mock인 API

진단·플랜·블록 완료는 엔진이 연결되기 전까지 가짜 데이터를 돌려줍니다. 이 상태는 서버를 재시작하면 사라집니다. 코드 실행(`/run`)은 아래처럼 실제로 실행합니다.

### 코드 실행 샌드박스

`POST /run`이 작업을 Redis 큐에 넣으면 worker 컨테이너가 꺼내서 작업마다 새 `bridge-sandbox` 컨테이너(gcc, python)로 실행합니다. 화면은 `GET /run/{jobId}`를 0.5초마다 불러서 `status`가 `queued` → `running` → `done`이 되면 결과를 보여 주면 됩니다.

| 제한 | 값 |
| --- | --- |
| 실행 시간 | 5초 (넘으면 `timedOut: true`, `exitCode: 124`) |
| 컴파일 시간 | 10초 |
| 메모리 / CPU / 프로세스 | 128MB / 0.5개 / 64개 |
| 출력 | 64KB (넘는 부분은 잘림) |
| 네트워크 | 차단 |
| 파일 쓰기 | `/tmp`(16MB)만 |
| 동시 실행 | 4개, 나머지는 큐에서 대기 |

- 컴파일 에러는 `stderr`에 gcc 메시지가 그대로 오고 `exitCode`가 0이 아닙니다.
- `blockId`를 보내면 블록의 정답 출력과 비교해서 `matchesExpected`를 줍니다 (줄 끝 공백·마지막 줄바꿈 차이는 무시).
- 대기열에서 60초 넘게 기다린 작업은 실행하지 않고, 실행을 시작하고 45초 안에 결과가 없는 작업은 실패(`exitCode: 1`)로 돌려줍니다.
- 학생 코드가 실행기의 출력에 직접 쓰는 우회를 막았고, worker는 컨테이너 출력을 1MB까지만 받습니다. worker에는 Redis 주소만 넘깁니다 (DB 비밀번호·JWT 키 없음).
- 결과는 1시간 동안 보관합니다.

`docker compose up -d --build`를 하면 샌드박스 이미지 빌드와 worker 실행까지 같이 됩니다. worker는 호스트의 Docker(`/var/run/docker.sock`)로 컨테이너를 띄웁니다.

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

API·DB 테스트는 `docker compose up -d`로 postgres가 떠 있을 때만 실행되고, 없으면 건너뜁니다. 실제 샌드박스 테스트(`tests/test_sandbox.py`)는 `bridge-sandbox` 이미지와 `docker` 명령이 있을 때만 실행됩니다. PR을 올리기 전에는 `REQUIRE_DB=1 pytest`로 돌려서 건너뛴 테스트 없이 모두 통과하는지 확인하세요. Redis는 테스트용 가짜(fakeredis)를 씁니다. 테스트 데이터는 끝나면 되돌려서 DB에 남지 않습니다.

개발 규칙은 [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)를 참고하세요.
