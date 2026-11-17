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

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | /health | 서버 상태 확인 |

개발 규칙은 [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)를 참고하세요.
