// 백엔드 API 호출은 모두 이 파일을 거친다.
// 경로는 개발 가이드 4장 API 명세를 따른다. 백엔드 라우터에는 /api 접두어가 없으므로
// 여기 경로에도 /api를 넣지 않는다. 접두어는 API_BASE가 붙이고, 개발 서버 프록시와
// 배포 Caddy가 떼어서 백엔드로 넘긴다 (/api/auth/login → /auth/login).
// JSON 요청·응답 필드는 모두 camelCase다.
// 요청·응답 타입은 mock API(A3, PR #28)의 backend/app/api/schemas.py를 따른다.
// 아직 unknown인 함수는 해당 화면을 만들 때 구체화한다.

const API_BASE: string = import.meta.env.VITE_API_BASE || '/api'

// 토큰은 메모리에만 둔다. 사지방 PC는 재부팅하면 초기화되므로 브라우저 저장소를 쓰지 않는다.
let authToken: string | null = null

export function setAuthToken(token: string | null): void {
  authToken = token
}

export function getAuthToken(): string | null {
  return authToken
}

// 실패 응답. 백엔드가 { "detail": "..." } 형태로 보낸 안내 문구는 detail과 message에 담긴다.
// 예) 401 { "detail": "아이디 또는 PIN이 틀렸어요" }, 429 { "detail": "1분 후 다시 시도해 주세요" }
export class ApiError extends Error {
  status: number
  body: unknown
  detail: string | null

  constructor(status: number, body: unknown) {
    const detail = extractDetail(body)
    super(detail ?? `API 요청 실패 (${status})`)
    this.name = 'ApiError'
    this.status = status
    this.body = body
    this.detail = detail
  }
}

// detail이 문자열일 때만 꺼낸다. (FastAPI 입력 검증 오류 422는 detail이 배열이라 제외)
function extractDetail(body: unknown): string | null {
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const { detail } = body as { detail: unknown }
    if (typeof detail === 'string') return detail
  }
  return null
}

type HttpMethod = 'GET' | 'POST' | 'PUT'

async function request<T>(method: HttpMethod, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  const data = parseBody(await res.text())

  if (!res.ok) throw new ApiError(res.status, data)
  return data as T
}

// 빈 본문은 null, JSON이 아니면 원문 텍스트를 그대로 돌려준다.
// (예: 서버 내부 오류 시 FastAPI가 보내는 "Internal Server Error")
function parseBody(text: string): unknown {
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

// ---- 인증·프로필 ----

export interface LoginRequest {
  loginId: string
  pin: string
}

export interface LoginResponse {
  token: string
  isNewUser: boolean
}

/**
 * POST /auth/login: 아이디 + PIN → 토큰 (없는 아이디면 가입)
 * 실패: 401 아이디 또는 PIN 틀림, 429 연속 실패로 1분 잠금 → ApiError(status, detail)
 */
export function login(loginId: string, pin: string) {
  const body: LoginRequest = { loginId, pin }
  return request<LoginResponse>('POST', '/auth/login', body)
}

// 성적표의 원래 성적. 정규화(A/B/C, 미이수)는 백엔드가 한다.
export const GRADES = [
  'A+', 'A0', 'A-',
  'B+', 'B0', 'B-',
  'C+', 'C0', 'C-',
  'D+', 'D0', 'D-',
  'F', 'P',
] as const

export type Grade = (typeof GRADES)[number]

/** 과목 코드. content/concepts.json의 course와 같다 (C: C 프로그래밍, DS: 자료구조). */
export type CourseCode = 'C' | 'DS'

export interface CompletedCourse {
  course: CourseCode
  /** 성적표의 원래 성적 */
  grade: Grade
}

export interface Profile {
  /** 이수한 과목과 성적. 미수강 과목은 넣지 않는다. */
  completedCourses: CompletedCourse[]
  /** 0~120 */
  gapMonths: number
  targetCourse: CourseCode
  /** YYYY-MM-DD */
  returnDate: string
  /** 30~600 */
  dailyMinutes: number
}

export interface ProfileResponse extends Profile {
  updatedAt: string
}

/**
 * PUT /profile: 이수 과목·공백·복학일·하루 시간 저장
 * 실패: 422 입력 검증 오류 (detail은 배열) → ApiError(status, detail=null)
 */
export function saveProfile(profile: Profile) {
  return request<ProfileResponse>('PUT', '/profile', profile)
}

// ---- 진단 ----

/** 화면에 보여줄 문제. 정답은 내려오지 않는다. */
export interface QuestionOut {
  id: string
  conceptId: string
  conceptName: string
  prompt: string
  /** 코드 문제일 때 하이라이트할 코드. 없으면 null */
  code: string | null
  choices: string[]
}

export interface DiagnosisAnswerRequest {
  questionId: string
  /** choices의 0부터 시작하는 인덱스 */
  choice: number
}

/** 진단 시작·답 제출 응답. done이 true이면 question은 null. */
export interface DiagnosisStep {
  done: boolean
  /** 방금 낸 답의 정답 여부 (start에서는 null) */
  correct: boolean | null
  question: QuestionOut | null
  /** 지금까지 답한 문제 수 (지금 문제는 포함하지 않음) */
  answeredCount: number
  maxQuestions: number
}

export interface ConceptResult {
  id: string
  name: string
  course: string
  prereqs: string[]
  /** 0~1. 그래프 색깔에 사용 */
  mastery: number
  /** prior: 망각 추정값, diagnosed: 진단 문제로 확인한 값 */
  source: 'prior' | 'diagnosed'
}

export interface DiagnosisResult {
  concepts: ConceptResult[]
}

/** POST /diagnosis/start: 시작점 계산 후 첫 문제 반환 */
export function startDiagnosis() {
  return request<DiagnosisStep>('POST', '/diagnosis/start')
}

/**
 * POST /diagnosis/answer: 답 제출 → 다음 문제 또는 종료
 * 실패: 400 이미 끝난 진단이거나 지금 문제가 아닌 답 → ApiError(status, detail)
 */
export function answerDiagnosis(questionId: string, choice: number) {
  const body: DiagnosisAnswerRequest = { questionId, choice }
  return request<DiagnosisStep>('POST', '/diagnosis/answer', body)
}

/** GET /diagnosis/result: 개념별 mastery (그래프용) */
export function getDiagnosisResult() {
  return request<DiagnosisResult>('GET', '/diagnosis/result')
}

// ---- 플랜 ----

/** POST /plan/generate: 역산 플랜 생성 */
export function generatePlan() {
  return request<unknown>('POST', '/plan/generate')
}

/** GET /plan: 날짜별 블록 목록, 오늘 남은 시간 */
export function getPlan() {
  return request<unknown>('GET', '/plan')
}

// ---- 블록 학습 ----

/** GET /blocks/{id}: 강의 링크·실습·확인 문제 */
export function getBlock(blockId: string) {
  return request<unknown>('GET', `/blocks/${encodeURIComponent(blockId)}`)
}

/** POST /blocks/{id}/complete: 블록 완료 처리 */
export function completeBlock(blockId: string) {
  return request<unknown>('POST', `/blocks/${encodeURIComponent(blockId)}/complete`)
}

/** PUT /code/{blockId}: 코드 자동 저장 */
export function saveCode(blockId: string, code: string) {
  return request<unknown>('PUT', `/code/${encodeURIComponent(blockId)}`, { code })
}

// ---- 코드 실행 ----

/** POST /run: 코드 실행 요청 → jobId */
export function runCode(payload: unknown) {
  return request<unknown>('POST', '/run', payload)
}

/** GET /run/{jobId}: 실행 결과 (출력, 에러, 시간 초과) */
export function getRunResult(jobId: string) {
  return request<unknown>('GET', `/run/${encodeURIComponent(jobId)}`)
}
