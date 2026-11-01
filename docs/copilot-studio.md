# Copilot Studio 에이전트 연결 가이드

역할 나누기
- **Copilot Studio**: 팀장·분석 에이전트의 판단(조건 해석, 질문 만들기)
- **백엔드(이 저장소)**: 입력 보관, 신호·비상정지 점검, 상태 머신(`jobs`), 기록(`job_events`)

```
(A) 사용자 → 웹 화면 "분석 시작" → 백엔드가 작업(job) 생성 → Direct Line으로 팀장 에이전트 호출
(B) 팀장 에이전트 → getJob(입력 읽기) → 분석 에이전트 → submitRequirements → 백엔드 점검
  → 질문이 있으면 NEEDS_INPUT (화면에 질문 표시) / 없으면 DESIGNING
웹 화면은 /projects/{id}/status를 2초마다 조회해 진행 상황을 보여 줘요.
```

## 1. 백엔드 준비

1. 서버 환경변수 `AGENT_API_KEY`에 길고 무작위인 값을 넣고 백엔드를 다시 켜요. 키는 저장소에 올리지 마세요.
2. Copilot Studio는 인터넷에서 백엔드에 접근해야 해요. `localhost`는 안 돼요.
   - 임시: Dev Tunnel 등으로 8000 포트를 공개 (`devtunnel host -p 8000 --allow-anonymous` — 익명 접근을 열어도 `/agent/*`는 API 키가 막아 줘요)
   - 정식: 이슈 #45의 배포 주소
3. `https://<공개주소>/agent-spec.json`이 열리는지 확인해요.
4. (방향 A) Copilot Studio 에이전트 → **설정 → 보안 → 웹 채널 보안**에서 Direct Line 시크릿 또는 토큰 엔드포인트를 확인해, 백엔드 환경변수에 넣어요.

| 환경변수 | 뜻 |
|---|---|
| `COPILOT_DIRECTLINE_SECRET` | Direct Line 시크릿 (또는 아래 토큰 엔드포인트 중 하나) |
| `COPILOT_TOKEN_ENDPOINT` | Copilot Studio 토큰 엔드포인트 URL |
| `COPILOT_DIRECTLINE_URL` | 기본 `https://directline.botframework.com/v3/directline` |
| `COPILOT_TIMEOUT_SECONDS` | 에이전트 응답 대기 시간(기본 180초). 넘으면 작업이 `FAILED`가 돼요 |
| `AGENT_DEMO=1` | 에이전트 없이 화면 흐름만 보는 **시연 모드**(실제 AI 분석 아님) |

둘 다 없고 시연 모드도 아니면 "분석 시작" 버튼은 비활성이고 `/projects/{id}/run`은 503이에요.

## 2. 도구 추가

### 방법 1: MCP (REST API 메뉴가 없을 때 추천)
Copilot Studio → 에이전트 → **도구 → 도구 추가 → `+ 추가` → 모델 컨텍스트 프로토콜(MCP)**
- 서버 URL: `https://<공개주소>/mcp`
- 인증: **API 키**, 위치 **헤더**, 이름 `X-API-Key`, 값은 `AGENT_API_KEY`
- 도구 5개(`getJob`, `submitRequirements`, `getStatus`, `reportVerification`, `startJob`)가 REST와 똑같이 생겨요. (구현: `app/mcp_api.py`)

### 방법 2: REST API

Copilot Studio → 에이전트 → **도구 → 도구 추가 → REST API** → `agent-spec.json` 가져오기.
- 인증: **API 키**, 위치 **헤더**, 이름 `X-API-Key`, 값은 `AGENT_API_KEY`
- 가져오면 도구 5개가 생겨요: `getJob`, `submitRequirements`, `getStatus`, `reportVerification`, `startJob`
- 홈페이지에서 시작하는 흐름(A)에서는 `getJob`과 `submitRequirements`를 써요. `startJob`은 에이전트가 직접 시작하는 방식(B 단독)용이에요.

## 3. 에이전트 만들기

### 팀장 에이전트 (지침)
```
당신은 MELSEC PLC 회로 설계 팀의 팀장입니다. 백엔드가 "[작업 시작] project_id=... job_id=..." 형태의 메시지를 보내면 다음 순서로 일합니다.
1. getJob 도구에 job_id를 넣어 작업 입력(project)과 사용자 답변(answers)을 읽고, 분석 에이전트에게 넘깁니다. 이미 답변한 질문은 다시 묻지 않습니다. (질문에 답하면 웹 화면이 새 작업을 만들어 answers와 함께 다시 실행해요.)
   - 백엔드는 "잠시", "적당히" 같은 모호한 표현이 숫자 없이 있으면 직접 질문을 추가해요.
2. 분석 에이전트의 결과를 submitRequirements 도구로 제출합니다. job_id는 메시지에 있는 값을 그대로 씁니다.
3. 결과 state가 NEEDS_INPUT이면 "추가 정보가 필요해요"라고 알립니다. 질문은 웹 화면이 보여 주므로 새 작업을 만들지 않습니다.
4. state가 DESIGNING이면 "분석이 끝났고 설계 단계로 넘어갔다"고 알립니다. (설계·검증은 이후 단계에서 연결합니다.)
5. 진행 상황을 물으면 getStatus로 확인해 알려 줍니다.
절대 회로가 안전하다고 단정하지 말고, 실제 설비 적용 전 전문가 확인이 필요하다고 안내합니다.
상태 값(state)은 도구 결과를 그대로 전달하고 추측하지 않습니다.
```

### 분석 에이전트 (지침)
```
당신은 MELSEC PLC 제어 요구사항 분석가입니다. 입력으로 plc_config, io_list, conditions를 받습니다.
동작 조건 문장을 조건 목록으로 나눠 아래 JSON 모양으로만 답합니다.
{
  "conditions": [{"type": "sequence|interlock|timing|safety|alarm", "text": "...", "must_pass": true, "signals": ["START","Y0"]}],
  "timers": [{"name": "...", "preset_ms": 0, "purpose": "..."}],
  "counters": [{"name": "...", "preset": 0, "purpose": "..."}],
  "assumptions": ["추측한 내용"],
  "questions": ["사용자에게 물을 질문"]
}
규칙
- signals에는 io_list의 디바이스(X1) 또는 이름(START)만 적습니다. 목록에 없는 신호를 만들어 내지 않습니다.
- 질문은 꼭 필요한 것만 최대 3개 씁니다. 안전과 직결되거나 값이 없으면 회로를 못 만드는 것(없는 신호, 시간 값)만 질문합니다.
- 그 외 모호한 조건(정지 방식, 재기동, 보호 입력, 시간 제한 등)은 질문하지 말고 가장 일반적인 방식으로 가정해 assumptions에 적습니다.
- 사용자 답변(answers)에 이미 있는 내용은 다시 묻지 않고 그 값을 사용합니다.
- 비상정지(emergency_stop)가 사용 설정이면 "모든 출력 OFF" 조건을 safety로 포함합니다.
- 설명 문장 없이 JSON만 출력합니다.
```

팀장 에이전트의 **연결된 에이전트**로 분석 에이전트를 추가하고, 도구 4개는 팀장에게 연결해요.

## 4. 시험

1. 웹 화면에서 프로젝트를 저장하고 "분석 시작"을 눌러요. (에이전트 없이 화면만 보려면 `AGENT_DEMO=1`)
2. 또는 Copilot Studio 테스트 창에 "[작업 시작] project_id=<ID> job_id=<JOB>"처럼 입력 (job은 `POST /projects/<ID>/run`으로 만들어요)
3. 기대 결과: 조건이 `C1, C2…`로 나뉘고, I/O에 없는 신호가 있으면 질문이 나오며, 없으면 `DESIGNING`
4. `GET /projects/<ID>/status`로 단계 기록 확인

## 다음 구현이 이어 붙이는 자리

| 이슈 | 이어 붙일 곳 | 입력 → 출력 (계약: `app/contracts.py`) |
|---|---|---|
| #41 설계 | `DESIGNING` 상태에서 호출 | `StructuredRequirements` → `Ir`. 끝나면 `VERIFYING`으로 |
| #42 검증 | `VERIFYING` 상태에서 호출 | `Ir` → `VerificationResult`. 결과는 `reportVerification`/`orchestrator.report_verification`으로 |
| #43 수정 | `FIXING` 상태 | `VerificationResult.errors` → 고친 `Ir` |
| #44 파일 생성 | `COMPLETED → GENERATING → DELIVERED` | `Ir` → GX Works 파일 |

분석 결과는 `job_events`의 `requirements` 이벤트(`data`가 `StructuredRequirements`)에 저장돼요. 상태 전이는 `app/agents/orchestrator.py`의 `_move()`만 사용해 주세요.

## 주의
- 입력한 I/O 목록과 조건은 Microsoft 서비스로 전송돼요. 기밀 도면은 조직 정책을 확인한 뒤 사용하세요.
- 에이전트 도구 호출 결과가 틀려도 백엔드가 신호 존재 여부와 비상정지를 다시 점검하지만, 회로 안전은 보장하지 않아요.
