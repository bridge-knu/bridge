# 브릿지 개발 규칙

학업 공백 학생(복학·편입·전과)을 위한 선수 개념 진단·학습 플랜 서비스.

## 기술 스택
- Frontend: React + TypeScript (Vite)
- Backend: FastAPI (Python 3.11)
- DB: PostgreSQL / Queue: Redis
- 실행 환경: Docker Compose

## 폴더 구조와 담당
| 폴더 | 담당 | 내용 |
| --- | --- | --- |
| backend/app/api, models | 상민 | API, DB 모델 |
| sandbox/, deploy/ | 상민 | 코드 실행 샌드박스, 배포 |
| backend/app/engine | 준혁 | 망각 추정·진단·플랜 엔진 |
| content/ | 준혁 | 개념 지도·문제·블록 JSON |
| frontend/ | 민재 | 화면 전체 |
| content/academic_changes.json | 민재 | 학사 변경 안내 데이터 |

자기 폴더만 수정한다. 다른 폴더를 고쳐야 하면 먼저 말한다.

## 코드 원칙
- engine/은 DB를 모르는 순수 함수로 작성하고, 모든 함수에 pytest 테스트를 둔다.
- 콘텐츠는 content/*.json에 두고 DB에 넣지 않는다.
- API는 정해진 목록([DEVELOPMENT.md](DEVELOPMENT.md) 참고)을 따른다. 새 API는 만들기 전에 공유한다.
- 비밀번호·키는 .env에만 둔다. .env는 커밋하지 않는다.
- 코드와 주석에 생성 도구 관련 표시를 남기지 않는다.

## 작업 흐름
1. 칸반에서 이슈를 골라 내 이름을 배정하고 In progress로 옮긴다.
2. `git switch main && git pull`
3. `git switch -c 종류/이슈번호-내용` (예: feat/12-diagnosis-api)
4. 작게 자주 커밋하고 push한다.
5. PR 본문에 `Closes #이슈번호`와 변경 설명(파일별 5줄 이내)을 쓴다.
6. 팀원 1명 승인 후 Squash and merge.

main에 직접 push하지 않는다.

## 커밋 메시지
`종류: 한글 설명`
- feat: 새 기능 / fix: 버그 수정 / content: 개념·문제 데이터
- docs: 문서 / chore: 설정·빌드

예) `feat: 진단 시작 API 추가`

## 리뷰 기준 (5분)
- 로컬에서 실행되는가
- 기존 기능이 깨지지 않는가
- 비밀번호·키가 들어가지 않았는가
- 스타일 지적은 하지 않는다

## 기타
- 작업 전 항상 `git pull`, PR은 하루를 넘기지 않는다.
- 직접 실행해서 확인한 뒤에 PR을 올린다.
- 막히면 30분 안에 공유한다.
- 스탠드업: 매일 밤 10시, 오늘 한 것 / 내일 할 것 / 막힌 것
