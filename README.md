# bridge
학업 공백 학생을 위한 선수 개념 진단·학습 계획 서비스

## 실행 방법

필요한 것: [Docker Desktop](https://www.docker.com/products/docker-desktop/) (실행 중이어야 함)

```bash
git clone https://github.com/bridge-knu/bridge.git
cd bridge
cp .env.example .env
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

요청·응답 JSON 필드는 camelCase이고, 오류는 `{"detail": "안내 문구"}` 형태입니다. 필드별 모양은 http://localhost:8000/docs 에서 확인하세요.

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

### 지금은 mock API입니다

DB와 엔진이 연결되기 전까지 가짜 데이터를 돌려줍니다. 저장한 값은 서버를 재시작하면 사라집니다. 화면에서 오류 상황을 확인할 때 아래 값을 쓰세요.

| 상황 | 방법 |
| --- | --- |
| 기존 사용자 로그인 | 아이디 `demo` (그 외 아이디는 새 사용자) |
| PIN 틀림 (401) | PIN `9999` |
| 로그인 잠금 (429) | 아이디 `locked` |
| 코드 실행 시간 초과 | 코드에 `while (1)` 또는 `for (;;)` |
| 컴파일 에러 | 코드에 `COMPILE_ERROR` |

코드 실행은 1초 동안 `running`이었다가 `done`이 됩니다.

## 테스트

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

개발 규칙은 [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)를 참고하세요.
