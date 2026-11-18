# API 계약

프론트(C)와 백엔드(A)가 합의한 요청·응답 규격입니다. 경로 목록은 개발 가이드 4장을 따르고,
이 문서는 필드 형식과 규칙을 기록합니다. 바꿀 때는 먼저 공유하고 이 문서를 같이 고칩니다.

`[확인 필요: 이름]` 표시는 해당 담당자가 확인하기 전까지 잠정 규격이라는 뜻입니다. 확인되면 표시를 지웁니다.

## 공통 규칙

- 백엔드 라우터에는 `/api` 접두어를 쓰지 않는다. 경로는 `/auth/login`, `/profile`처럼 쓴다.
- 프론트는 `/api/...`로 요청하고, 개발 서버 프록시(Vite)와 배포(Caddy)가 `/api`를 떼고 백엔드로 넘긴다.
- JSON 요청·응답 필드는 모두 camelCase를 쓴다.
- DB와 엔진 내부에서는 snake_case를 써도 된다. 변환은 백엔드(API 스키마)에서 한다.
- 인증이 필요한 API는 `Authorization: Bearer <token>` 헤더를 쓴다.

> **[확인 필요: 상민]** mock은 토큰을 검사하지 않는다. 실제 인증이 붙으면 토큰이 없거나 만료됐을 때
> 401과 `detail` 문구를 어떻게 줄지 정해 주세요. 프론트는 401이면 로그인 화면으로 보낸다.

- 실패 응답은 `{ "detail": "안내 문구" }` 형태로, 화면에 그대로 보여줄 수 있는 문구를 담는다.

## POST /auth/login

아이디 + PIN으로 로그인한다. 없는 아이디면 가입한다.

요청:

```json
{ "loginId": "demo", "pin": "0000" }
```

성공 (200):

```json
{ "token": "eyJ...", "isNewUser": false }
```

실패:

| 상태 | 본문 |
| --- | --- |
| 401 | `{ "detail": "아이디 또는 PIN이 틀렸어요" }` |
| 429 | `{ "detail": "1분 후 다시 시도해 주세요" }` |

> **[확인 필요: 상민]** PR #28 스키마는 `loginId` 1~30자, `pin` 숫자 4자리이고 어기면 422(`detail` 배열)가 난다.
> 이 제한과 422 응답을 계약으로 확정할지 확인해 주세요. 프론트 입력칸도 30자·4자리로 막는다.

## PUT /profile

진단·플랜에 쓰는 프로필을 저장한다. 규격은 PR #28(`f3d10bf`)의 `backend/app/api/schemas.py`를 따른다.

요청:

```json
{
  "completedCourses": [
    { "course": "C", "grade": "B+" }
  ],
  "gapMonths": 24,
  "targetCourse": "DS",
  "returnDate": "2027-03-02",
  "dailyMinutes": 60
}
```

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `completedCourses` | `{ course: "C" \| "DS", grade: Grade }[]` | 이수한 과목과 성적. 미수강 과목은 넣지 않는다 (빈 배열 가능) |
| `gapMonths` | number | 공백 개월 수, 0~120 정수 |
| `targetCourse` | `"C" \| "DS"` | 목표 과목 |
| `returnDate` | string | 복학일, `YYYY-MM-DD` |
| `dailyMinutes` | number | 하루 가용 시간(분), 30~600 정수 |

과목 코드 `C`는 C 프로그래밍, `DS`는 자료구조이며 `content/concepts.json`의 `course`와 같다.

`Grade`는 성적표의 원래 성적 14개 중 하나다.

```
A+ A0 A- B+ B0 B- C+ C0 C- D+ D0 D- F P
```

성공 (200): 요청과 같은 필드에 저장 시각 `updatedAt`(ISO 8601, UTC)이 붙는다.

```json
{
  "completedCourses": [{ "course": "C", "grade": "B+" }],
  "gapMonths": 24,
  "targetCourse": "DS",
  "returnDate": "2027-03-02",
  "dailyMinutes": 60,
  "updatedAt": "2026-11-19T03:00:00.123456Z"
}
```

실패:

| 상태 | 본문 |
| --- | --- |
| 422 | FastAPI 입력 검증 오류. `detail`이 문자열이 아니라 배열이다 (예: `[{ "type": "list_type", "loc": ["body", "completedCourses"], "msg": "Input should be a valid list" }]`). 프론트는 일반 안내 문구를 보여준다 |

> **[확인 필요: 상민]** 아래 항목을 확인해 주세요.
> - `grade`: 현재 스키마는 `str | None`(선택값, 값 제한 없음)이다. PR #28 리뷰에서 필수 + 위 14개 값만 허용하도록
>   후속 변경이 요청되어 있다. 프론트는 이미 14개 값 중 하나만 보낸다.
> - 같은 과목이 두 번 들어온 경우(예: `C`가 2개) 처리가 정해져 있지 않다. 허용할지 422로 거부할지 정해 주세요.
> - `gapMonths` 0~120, `dailyMinutes` 30~600: 프론트 입력 검사가 이 범위를 그대로 쓴다. 확정 값인지 확인해 주세요.
> - `updatedAt`은 UTC(`...Z`)로 내려온다. 이 형식으로 확정할지 확인해 주세요.
> - 422는 FastAPI 기본 형식(`detail` 배열)이다. 프론트는 일반 안내 문구를 보여준다. 이대로 둘지 확인해 주세요.

### 성적 정규화

백엔드(API)는 성적을 **받은 그대로 저장**하고 변환하지 않는다. A/B/C로 바꾸는 일은 **엔진이 담당**한다
(`backend/app/engine/forgetting.py`의 `normalize_grade`).

> **[확인 필요: 준혁]** 아래 표는 `feat/11-forgetting` 브랜치의 `normalize_grade` 기준이며 아직 main에 없다.
> 엔진이 병합되면 값이 같은지 확인해 주세요.

| 원래 성적 | 정규화 | 엔진 base 값 |
| --- | --- | --- |
| A+, A0, A- | A | 0.9 |
| B+, B0, B- | B | 0.75 |
| C+, C0, C- | C | 0.6 |
| P | B | 0.75 |
| D+, D0, D-, F | 미이수 | 0.1 |

## 진단 API (C3 PR에서 기록)

`POST /diagnosis/start`, `POST /diagnosis/answer`, `GET /diagnosis/result`의 필드 형식은 PR #28에서 정해졌고,
진단 화면(C3, #18) PR에서 이 문서에 기록한다. 정답(`answer`)은 클라이언트로 보내지 않는다.
