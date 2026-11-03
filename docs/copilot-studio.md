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
- 도구 6개(`getJob`, `submitRequirements`, `generateDesign`, `getStatus`, `reportVerification`, `startJob`)가 REST와 똑같이 생겨요. (구현: `app/mcp_api.py`)

### 방법 2: REST API

Copilot Studio → 에이전트 → **도구 → 도구 추가 → REST API** → `agent-spec.json` 가져오기.
- 인증: **API 키**, 위치 **헤더**, 이름 `X-API-Key`, 값은 `AGENT_API_KEY`
- 가져오면 도구 6개가 생겨요: `getJob`, `submitRequirements`, `generateDesign`, `getStatus`, `reportVerification`, `startJob`
- 홈페이지에서 시작하는 흐름(A)에서는 `getJob`과 `submitRequirements`를 써요. `startJob`은 에이전트가 직접 시작하는 방식(B 단독)용이에요.

## 3. 에이전트 만들기

### 팀장 에이전트 (지침)
```
당신은 MELSEC PLC 회로 설계 팀의 팀장입니다. 백엔드가 "[작업 시작] project_id=... job_id=..." 형태의 메시지를 보내면 다음 순서로 일합니다.
1. getJob 도구에 job_id를 넣어 작업 입력(project)과 사용자 답변(answers)을 읽고, 분석 에이전트에게 넘깁니다. 이미 답변한 질문은 다시 묻지 않습니다. (질문에 답하면 웹 화면이 새 작업을 만들어 answers와 함께 다시 실행해요.)
   - 백엔드는 "잠시", "적당히" 같은 모호한 표현이 숫자 없이 있으면 직접 질문을 추가해요.
2. 분석 에이전트의 결과를 submitRequirements 도구로 제출합니다. job_id는 메시지에 있는 값을 그대로 씁니다.
3. 결과 state가 NEEDS_INPUT이면 "추가 정보가 필요해요"라고 알립니다. 질문은 웹 화면이 보여 주므로 새 작업을 만들지 않습니다.
4. 설계는 AI 없는 코드라 백엔드가 분석 직후 자동으로 `generateDesign`을 실행합니다(에이전트가 호출할 필요 없음). state가 DESIGNING이고 design 결과가 있으면 성공이며 안전 승인이 아닙니다. FAILED이면 실패 이유를 알리고 검증 단계로 넘기지 않습니다.
5. 진행 상황을 물으면 getStatus로 확인해 알려 줍니다.
절대 회로가 안전하다고 단정하지 말고, 실제 설비 적용 전 전문가 확인이 필요하다고 안내합니다.
상태 값(state)은 도구 결과를 그대로 전달하고 추측하지 않습니다.
```

### 분석 에이전트 (지침)
```
당신은 MELSEC PLC 제어 요구사항 분석가입니다. 입력으로 plc_config, io_list, conditions를 받습니다.
동작 조건 문장을 "회로 하나 = 조건 하나"가 되도록 나눠 아래 JSON 모양으로만 답합니다.
{
  "conditions": [{"type": "sequence|interlock|timing|safety", "text": "...", "must_pass": true, "signals": ["START","MOTOR"]}],
  "timers": [{"name": "...", "preset_ms": 0, "purpose": "..."}],
  "counters": [{"name": "...", "preset": 0, "purpose": "..."}],
  "assumptions": ["일반 가정 문장", "design.v1:{...}"],
  "questions": ["사용자에게 물을 질문"]
}

[조건 나누기]
- 한 출력(Y)을 켜는 동작은 조건 하나로만 만듭니다. 자기유지처럼 같은 출력의 시작·유지는 조건 하나(sequence)로 합치고, 같은 내용을 표현만 바꿔 여러 조건으로 쪼개지 않습니다.
- 정지·차단은 별도 조건 하나(interlock)로 둡니다. 정지 버튼이 여러 개면 한 조건에 모읍니다.
- 모든 조건에는 design.v1 지시문이 정확히 하나씩 있어야 합니다. 조건 id는 C1, C2... 순서대로입니다.
- signals에는 io_list의 이름(name)만 적고, 같은 신호를 주소와 이름으로 두 번 적지 않습니다. 해당 조건의 지시문에 나오는 입력과 출력만 적습니다. 목록에 없는 신호를 만들지 않습니다.

[design.v1 지시문] assumptions에 문자열로 추가합니다. 조건 하나당 JSON 객체 하나이고 "design.v1:" 바로 뒤에 붙입니다.
- 자기유지(sequence): design.v1:{"condition_id":"C1","mode":"self_hold","inputs":[{"signal":"START","active":"on"}],"join":"all","outputs":["MOTOR"]}
- 누르는 동안만 켜짐(sequence): mode를 "direct"로 바꿉니다. 나머지는 같습니다.
- 정지·차단(interlock): design.v1:{"condition_id":"C2","mode":"block","inputs":[{"signal":"STOP","active":"off"}],"join":"all","outputs":["MOTOR"]}
- 지연 켜짐(timing): design.v1:{"condition_id":"C1","mode":"on_delay","inputs":[...],"join":"all","outputs":["MOTOR"],"timer":"T_DELAY"} 그리고 timers에 같은 이름을 넣습니다.
- 횟수(sequence): mode "count", "counter":"이름", "reset":"none"을 추가합니다. counters에 같은 이름을 넣습니다.
- 서로 막는 인터록(interlock): 한쪽을 켤 때 다른 쪽을 막습니다. 예 FWD가 켜지면 REV 차단: {"mode":"block","inputs":[{"signal":"FWD","active":"on"}],"outputs":["REV"],"join":"all", ...}
- 비상정지가 사용 설정이면 safety 조건 하나를 넣고 signals는 비상정지 버튼 하나만 적습니다: design.v1:{"condition_id":"C9","mode":"emergency_stop"}
- active는 그 입력의 원시 값이 on/off일 때 조건이 참이라는 뜻입니다. 푸시버튼 NO를 누르면 "on", 푸시버튼 NC를 누르면 "off"입니다. 센서는 감지될 때의 값입니다.
- join은 입력이 모두 참이어야 하면 "all", 하나라도 참이면 "any"입니다.
- 위 형태로 표현할 수 없는 동작은 지시문을 만들지 말고 질문하세요.

[질문과 가정]
- 질문은 꼭 필요한 것만 씁니다. 0~3개이며, 억지로 채우지 않습니다. 같은 내용을 표현만 바꿔 두 번 묻지 않습니다.
- 질문 대상은 안전과 직결되거나 값이 없으면 회로를 못 만드는 것(없는 신호, 시간 값, 버튼으로 켜는데 유지인지 누르는 동안만인지 불명확한 경우)뿐입니다.
- 그 외 모호한 세부 동작(재기동, 보호 입력 등)은 질문하지 말고 가장 일반적인 방식으로 가정해 일반 가정 문장으로 assumptions에 적습니다.
- 사용자 답변(answers)에 이미 있는 내용은 다시 묻지 않고 그 값을 사용합니다.
- 설명 문장 없이 JSON만 출력합니다.
```

팀장 에이전트의 **연결된 에이전트**로 분석 에이전트를 추가하고, 흐름(A)에서 쓰는 `getJob`, `submitRequirements`, `generateDesign`, `getStatus` 도구를 팀장에게 연결해요. 실제 Studio 설정·게시·호출 검증은 담당자가 직접 해야 해요.

## 설계 함수용 명시 입력 규약 (`design.v1`)

`Condition.type`, `signals`, I/O의 `kind`만으로 자기유지인지 순간출력인지, 정지 극성·인터록 방향·타이머 연결을 확정할 수 없어요.
**기존 분석 지침만으로 만든 결과는 그대로 설계할 수 없어요.** 팀장이 아래 기계 입력 규약을 사용자에게 확인한 뒤
분석 결과의 `assumptions`에 추가하고 `submitRequirements`로 제출해야 해요. 기존 작업의 분석 결과를 고치는 도구는 이번에 추가하지 않았어요.
공용 `contracts.py` 필드는 그대로지만, 이는 설계 단계의 새 의미 규약이에요. 일반 가정문·조건 문장을 명령으로 해석하거나 자동 기본값을 적용하지 않아요.

`assumptions`의 각 문자열은 `design.v1:`로 시작하고 **조건 하나당 JSON 객체 하나**를 담아요.

> **자동 생성(`app/plc/directives.py`)**: 분석 에이전트가 지시문을 만들지 않아도, `generateDesign`이 지시문이 없는 조건에 한해 코드로 만들어요(신호 종류·조건 type·'유지/동안/정지/또는' 같은 뚜렷한 단서 사용). 모호하면(예: 버튼으로 시작하는데 유지인지 누르는 동안인지 불명) 만들지 않고 실패 이유에 조건 ID와 함께 알려요. 에이전트가 직접 쓴 지시문은 항상 우선해요.
다음은 자기유지 예제 문장에 근거한 **시험용 값**이며, 사용자 설비 동작을 승인한 값이 아니에요.

```json
{
  "assumptions": [
    "design.v1:{\"condition_id\":\"C1\",\"mode\":\"self_hold\",\"inputs\":[{\"signal\":\"START\",\"active\":\"on\"}],\"join\":\"all\",\"outputs\":[\"MOTOR\"]}",
    "design.v1:{\"condition_id\":\"C2\",\"mode\":\"block\",\"inputs\":[{\"signal\":\"STOP\",\"active\":\"off\"}],\"join\":\"all\",\"outputs\":[\"MOTOR\"]}"
  ]
}
```

| 항목 | 정확한 의미 |
| --- | --- |
| `condition_id` | 비어 있지 않고 중복 없는 기존 조건 ID. 모든 조건에 지시가 필요해요(`must_pass:false`도 무시하지 않아요). |
| `inputs` | `signal`은 등록 I/O 이름 또는 X/Y 주소, `active`는 원시 입력값이 `on`/`off`일 때 참이라는 뜻이에요. 극성은 반드시 명시해요. |
| `join` | `all`은 모든 입력이 참(직렬), `any`는 하나라도 참(병렬)이에요. |
| `outputs` | 실제 구동·차단할 등록 Y 출력 목록. 신호 종류는 모터·램프·솔레노이드만 지원해요. |
| `timer` / `counter` | `TimerSpec.name` / `CounterSpec.name` 하나와 명시적으로 연결해요. 이름은 실제 할당 주소가 아니에요. |

| 조건 type / mode | 필요한 JSON 항목과 동작 |
| --- | --- |
| `sequence` / `direct` | `condition_id, mode, inputs, join, outputs`. 조건이 참인 동안 OUT, 거짓이면 OFF. |
| `sequence` / `self_hold` | 위 항목. 시작 조건과 출력 피드백을 병렬로 연결해요. 여러 출력은 M 하나로 함께 유지하고 같은 정지·인터록을 적용해야 해요. 정지·차단 조건은 별도 `block` 지시로 명시해요. |
| `interlock` / `block` | 위 항목. `inputs`와 `join`이 참이면 `outputs`를 차단해요. 출력마다 지시의 반대 논리를 직렬로 넣어요. 예: 평상시 ON인 NC STOP의 `active:off` → 허용 접점 NO. FWD ON 시 REV 차단은 `inputs:[FWD/on], outputs:[REV]`로 방향을 명시해요. |
| `timing` / `on_delay` | 위 항목 + `timer`. 입력 조건이 참이면 TON, 완료 접점으로 출력해요. 입력·인터록·비상정지는 타이머 렁과 최종 출력 렁 모두에 적용해요. 시간은 100ms 배수 K1~K32767만 지원해요. |
| `sequence` / `count` | 위 항목 + `counter, reset:"none"`. CTU 완료 접점으로 출력해요. 리셋하지 않는 누적 초안만 지원하며 실제 PLC 카운트·보존 동작은 미검증이에요. |
| `safety` / `emergency_stop` | **`condition_id, mode`만** 써요. `cfg.emergency_stop.used`가 참이어야 하고, 이 조건의 signals는 설정된 비상정지 X 하나여야 해요. I/O kind는 `푸시버튼 NC`(평상시 ON). 래더 NO로 모든 구동 렁에 직렬 적용해요. |

필수 항목 누락·추가 항목·중복 JSON 키·중복 조건·등록되지 않은 신호·signals 불일치·미연결/중복 타이머·순환 출력 참조·구동하지 않는 출력의 인터록은
조건 번호가 있는 `DesignError`가 돼요. 같은 렁에서 함께 구동하는 출력은 정지·인터록 지시가 같아야 하며 다르면 조건을 나눠야 해요.
입력 X는 푸시버튼 NO/NC·센서·리미트스위치만 지원해요. 출력 Y를 조건 접점으로 쓰려면 해당 출력을 만드는 조건도 있어야 해요.
각 출력은 한 구동 조건만 가져야 해요. 자기유지 피드백 외의 출력 참조 순환은 지원하지 않아요.
Q 래더·호환 CPU·GX Works2/GX Developer·자동 모드만 지원해요. ST, 보존/경보/추가 모듈/다중 운전 모드, 리셋 카운터, 일반 자연어 설계는 미지원이에요.

내부 주소는 `cfg.device_rule.M/T/C`에서 시작해요. 기준 데이터의 Q `internal_limits`가 있으면 **끝값 미포함** 상한으로 사용해요.
현재 `plc_spec.json`에는 상한이 없어서 `design.py`의 **매뉴얼 미확인 임시값** M8192/T2048/C1024를 사용하고 결과 `limitations`에 밝혀요.
내부 M/T/C를 실제 I/O 표인 것처럼 꾸미지 않아요. CPU 점수 또한 `verified:false`이며 실제 범위를 보증하지 않아요.

설계 함수는 AI를 호출하지 않고 `validate_ir` → `to_il`로 검사해 END를 포함한 IL을 반환해요.
REST는 `POST /agent/jobs/{job_id}/design`(통합 서버에서는 `/api/agent/jobs/{job_id}/design`),
MCP는 `generateDesign`에 `job_id` 문자열 하나만 보내요. 기존 `X-API-Key` 인증을 그대로 사용해요.
성공 응답은 기존 상태 정보 + `design`(IR, 실제 사용 I/O, 조건별 설명, 가정·한계, IL)이에요.
`design` 이벤트가 이미 있으면 재생성하지 않아요. 성공해도 **DESIGNING 유지**이며 다음 단계 호출·안전 승인은 하지 않아요.
설계나 저장된 계약 형식이 잘못되면 `design_error` 이유를 남기고 기존 `fail_job`으로 FAILED 처리해요.
REST의 설계 실패는 HTTP 200 안에 `state:FAILED, design:null, reason`이므로 상태를 반드시 확인해요.
MCP는 같은 내용을 JSON 텍스트로 반환하고 `isError:true`로 표시해요. 없는 작업은 404, 다른 상태에서 호출하면 409예요.

`backend/tests/fixtures/design_cases.json`은 기존 예제 3개의 입력에 지시를 덧붙이는 시험 데이터예요.
`estop_interlock.json`의 기존 문장 C2는 FWD→REV 차단인데 기존 고정 IR은 반대 방향만 반영했어요.
새 시험은 기존 파일을 수정하지 않고 X3(역방향 시작), C4(역방향 순간 구동), C5(STOP으로 두 출력 정지)를 **시험용으로** 추가해
REV를 실제 구동하는 렁에서 C2를 차단하는지 검사해요. 기존 `expected_il.json`을 정답으로 복제하지 않아요.

## 4. 시험

1. 웹 화면에서 프로젝트를 저장하고 "분석 시작"을 눌러요. (에이전트 없이 화면만 보려면 `AGENT_DEMO=1`)
2. 또는 Copilot Studio 테스트 창에 "[작업 시작] project_id=<ID> job_id=<JOB>"처럼 입력 (job은 `POST /projects/<ID>/run`으로 만들어요)
3. 기대 결과: 조건이 `C1, C2…`로 나뉘고, I/O에 없는 신호가 있으면 질문이 나오며, 없으면 `DESIGNING`
4. `GET /projects/<ID>/status`로 단계 기록 확인

## 다음 구현이 이어 붙이는 자리

| 이슈 | 이어 붙일 곳 | 입력 → 출력 (계약: `app/contracts.py`) |
|---|---|---|
| #41 설계 | `DESIGNING`에서 `generateDesign` 호출 | 명시 지시가 있는 `StructuredRequirements` → 초안 저장. 상태는 `DESIGNING` 유지. `VERIFYING` 연결은 이번 범위 밖 |
| #42 검증 | `VERIFYING` 상태에서 호출 | `Ir` → `VerificationResult`. 결과는 `reportVerification`/`orchestrator.report_verification`으로 |
| #43 수정 | `FIXING` 상태 | `VerificationResult.errors` → 고친 `Ir` |
| #44 파일 생성 | `COMPLETED → GENERATING → DELIVERED` | `Ir` → GX Works 파일 |

분석 결과는 `job_events`의 `requirements` 이벤트(`data`가 `StructuredRequirements`)에 저장돼요. 상태 전이는 `app/agents/orchestrator.py`의 `_move()`만 사용해 주세요.

## 주의
- 입력한 I/O 목록과 조건은 Microsoft 서비스로 전송돼요. 기밀 도면은 조직 정책을 확인한 뒤 사용하세요.
- 에이전트 도구 호출 결과가 틀려도 백엔드가 신호 존재 여부와 비상정지를 다시 점검하지만, 회로 안전은 보장하지 않아요.
