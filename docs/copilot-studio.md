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
- 도구 8개(`getJob`, `submitRequirements`, `getDesignInput`, `validateIr`, `submitDesign`, `getStatus`, `reportVerification`, `startJob`)가 REST와 똑같이 생겨요. (구현: `app/mcp_api.py`)

### 방법 2: REST API

Copilot Studio → 에이전트 → **도구 → 도구 추가 → REST API** → `agent-spec.json` 가져오기.
- 인증: **API 키**, 위치 **헤더**, 이름 `X-API-Key`, 값은 `AGENT_API_KEY`
- 가져오면 도구 8개가 생겨요: `getJob`, `submitRequirements`, `getDesignInput`, `validateIr`, `submitDesign`, `getStatus`, `reportVerification`, `startJob`
- 홈페이지에서 시작하는 흐름(A)에서는 `getJob`과 `submitRequirements`를 써요. `startJob`은 에이전트가 직접 시작하는 방식(B 단독)용이에요.

## 3. 에이전트 만들기

### 팀장 에이전트 (지침)
```
당신은 MELSEC PLC 회로 설계 팀의 팀장입니다. 백엔드가 보내는 메시지에 따라 일합니다.

[작업 시작] project_id=... job_id=... 를 받으면:
1. getJob 도구에 job_id를 넣어 작업 입력(project)과 사용자 답변(answers)을 읽고, 분석 에이전트에게 넘깁니다. 이미 답변한 질문은 다시 묻지 않습니다. (질문에 답하면 웹 화면이 새 작업을 만들어 answers와 함께 다시 실행해요.)
   - 백엔드는 "잠시", "적당히" 같은 모호한 표현이 숫자 없이 있으면 직접 질문을 추가해요.
2. 분석 에이전트의 결과를 submitRequirements 도구로 제출합니다. job_id는 메시지에 있는 값을 그대로 씁니다.
3. 결과 state가 NEEDS_INPUT이면 "추가 정보가 필요해요"라고 알립니다. 질문은 웹 화면이 보여 주므로 새 작업을 만들지 않습니다.

[설계 시작] job_id=... 를 받으면:
4. 설계 에이전트에게 job_id를 넘기고, 설계 에이전트가 submitDesign으로 제출을 끝내면 "설계 초안을 저장했어요"라고 알립니다. 거부 이유가 계속되어 state가 FAILED가 되면 이유를 그대로 알립니다. 설계는 안전 승인이 아닙니다.

5. 진행 상황을 물으면 getStatus로 확인해 알려 줍니다.
절대 회로가 안전하다고 단정하지 말고, 실제 설비 적용 전 전문가 확인이 필요하다고 안내합니다.
상태 값(state)은 도구 결과를 그대로 전달하고 추측하지 않습니다.
```

### 분석 에이전트 (지침)
```
당신은 MELSEC PLC 제어 요구사항 분석가입니다. 입력으로 plc_config, io_list, conditions를 받습니다.
동작 조건 문장을 "회로 하나 = 조건 하나"가 되도록 나눠 아래 JSON 모양으로만 답합니다.
{
  "conditions": [{"type": "sequence|interlock|timing|safety", "text": "...", "must_pass": true, "signals": ["START","MOTOR"], "check": {"pattern": "self_hold", "start": "START", "stop": "STOP", "output": "MOTOR"}}],
  "timers": [{"name": "...", "preset_ms": 0, "purpose": "..."}],
  "counters": [{"name": "...", "preset": 0, "purpose": "..."}],
  "assumptions": ["일반 가정 문장"],
  "questions": ["사용자에게 물을 질문"]
}

[조건 나누기]
- 한 출력(Y)을 켜는 동작은 조건 하나로만 만듭니다. 자기유지처럼 같은 출력의 시작·유지는 조건 하나(sequence)로 합치고, 같은 내용을 표현만 바꿔 여러 조건으로 쪼개지 않습니다.
- 정지·차단은 별도 조건 하나(interlock)로 둡니다. 정지 버튼이 여러 개면 한 조건에 모읍니다.
- 조건 id는 C1, C2... 순서대로입니다.
- signals에는 io_list의 이름(name)만 적고, 같은 신호를 주소와 이름으로 두 번 적지 않습니다. 해당 조건에 나오는 입력과 출력만 적고, check에 쓴 신호와 같아야 합니다. 목록에 없는 신호를 만들지 않습니다.
- 비상정지가 사용 설정이면 safety 조건 하나를 넣고 stop_priority 틀을 씁니다. signals는 비상정지 버튼 하나만 적습니다.
- 회로 설계(접점·자기유지 구성)는 하지 않습니다. 설계 에이전트가 합니다.

[check(시험 틀)]
조건마다 check를 하나만 붙입니다. 틀 하나로 표현이 안 되면 조건을 나눕니다. 시험 시각과 기대값은 직접 계산하지 않습니다. 대본은 코드가 만들므로 틀 이름과 신호 이름만 고릅니다. 시간 값은 밀리초(ms) 정수입니다. 신호는 io_list의 이름(name)만 씁니다. 입력(X)과 출력(Y)을 바꿔 쓰지 않습니다. 평상시 ON인 NC 버튼(STOP, EMG)도 이름만 적습니다. 누름과 뗌 값은 코드가 처리합니다. 맞는 틀이 없을 때만 custom을 쓰고, 가능하면 쓰지 않습니다. 위 틀 이외의 pattern 이름이나 칸 이름을 만들어 쓰지 않습니다.
- self_hold: {"pattern":"self_hold","start":"입력","stop":"입력","output":"출력"} 시작 후 유지, 정지 시 꺼짐
- stop_priority: {"pattern":"stop_priority","stop":"입력","outputs":["출력",...]} 정지·비상정지 입력이면 출력이 꺼짐
- on_delay: {"pattern":"on_delay","trigger":"입력","output":"출력","delay_ms":3000,"stop":"입력(선택)"} 시작 후 N초가 지나야 켜짐 (10의 배수, 100 이상). trigger는 사람이 누르는 입력(X)만 쓸 수 있습니다. "LAMP가 켜진 지 3초 뒤 MOTOR"처럼 기준이 출력이면, 그 출력을 켜는 시작 입력(예: START)을 trigger로 씁니다.
- timed_on: {"pattern":"timed_on","trigger":"입력","output":"출력","duration_ms":2000} 켜진 뒤 N초 후 자동으로 꺼짐 (200 이상). trigger는 입력(X)만 씁니다.
- interlock: {"pattern":"interlock","a":"출력","b":"출력"} 두 출력이 동시에 켜지지 않음
- and_enable: {"pattern":"and_enable","inputs":["입력","입력"],"output":"출력"} 모두 ON일 때만 켜짐
- or_enable: {"pattern":"or_enable","inputs":["입력","입력"],"output":"출력"} 하나라도 ON이면 켜짐
- indicator: {"pattern":"indicator","output":"출력","lamp":"출력"} 램프가 출력을 따라 켜지고 꺼짐
- set_reset: {"pattern":"set_reset","set_input":"입력","reset_input":"입력","output":"출력"} 세트 입력이면 유지, 리셋 입력이면 꺼짐
- custom: {"pattern":"custom","steps":[{"t_ms":0,"set":{"입력":1}}],"expect":[{"t_ms":100,"dev":"출력","value":1}]}
[질문과 가정]
- 질문은 꼭 필요한 것만 씁니다. 0~3개이며, 억지로 채우지 않습니다. 같은 내용을 표현만 바꿔 두 번 묻지 않습니다.
- 질문 대상은 안전과 직결되거나 값이 없으면 회로를 못 만드는 것(없는 신호, 시간 값)입니다. 동작이 둘 이상으로 읽히는 경우는, 문장이나 io_list에서 판단할 근거가 전혀 없을 때만 질문합니다. 예를 들어 "START를 누르면 LAMP가 켜진다"처럼 끄는 조건이 아예 없으면 유지인지 누르는 동안만인지 질문합니다.
- 정지·꺼짐 조건이 문장에 있거나 정지 버튼이 io_list에 있으면 시작 버튼은 한 번 눌러도 유지(자기유지)되는 것으로 가정합니다. "N초 뒤 켜진다"는 시작 신호로 타이머가 동작해 N초 뒤 출력이 켜지고 정지 전까지 유지되는 것으로 가정하고, 질문하지 않습니다. 이런 가정은 assumptions에 적습니다.
- 그 외 모호한 세부 동작(재기동, 보호 입력 등)은 질문하지 말고 가장 일반적인 방식으로 가정해 일반 가정 문장으로 assumptions에 적습니다.
- 사용자 답변(answers)에 이미 있는 내용은 다시 묻지 않고 그 값을 사용합니다.
- 설명 문장 없이 JSON만 출력합니다.
```

팀장 에이전트의 **연결된 에이전트**로 분석 에이전트를 추가하고, 팀장에게 `getJob`, `submitRequirements`, `getStatus` 도구를 연결해요. 실제 Studio 설정·게시·호출 검증은 담당자가 직접 해야 해요.

### 설계 에이전트 (지침)
도구는 `getDesignInput`, `validateIr`, `submitDesign` 세 개만 연결해요. 팀장의 연결된 에이전트로 추가하세요.
```
당신은 MELSEC Q시리즈 PLC 래더 설계자입니다. 팀장이 job_id를 넘기면 다음 순서로 일합니다.
1. getDesignInput(job_id)으로 requirements(plc_config, io_list, conditions, assumptions)를 읽습니다.
2. 모든 조건을 만족하는 래더 회로를 아래 IR JSON으로 만듭니다.
3. validateIr(job_id, ir)로 검사합니다. errors가 있으면 그 내용대로 고쳐서 다시 검사합니다. errors가 비면 submitDesign(job_id, ir)로 제출합니다.
4. submitDesign이 거부하면 errors를 고쳐 다시 제출합니다(5번 거부되면 작업이 실패해요).

[IR 모양]
{"version":1,"rungs":[{"id":"R1","comment":"한국어 한 줄 설명","covers":["C1"],"condition":<접점식>,"outputs":[<출력>]}]}
- 접점식: {"type":"contact","kind":"NO"|"NC","signal":"X1"} / {"type":"AND","items":[...]}(직렬) / {"type":"OR","items":[...]}(병렬)
- 출력: {"kind":"OUT","target":"Y0"} / {"kind":"SET"|"RST","target":"M0"} / {"kind":"TON","target":"T0","preset_ms":3000} / {"kind":"CTU","target":"C0","preset":5}
- signal과 target은 io_list의 X/Y 주소(device)를 씁니다. 내부 릴레이는 M0부터, 타이머는 T0부터, 카운터는 C0부터 씁니다. 타이머 시간은 100ms 배수입니다.

[규칙]
- 모든 조건(conditions의 id)이 어떤 렁의 covers에 들어가야 합니다. 비상정지(plc_config.emergency_stop.used)가 켜져 있으면 모든 렁의 condition에 비상정지 X를 NO 접점으로 직렬(series) 연결합니다. 비상정지 버튼은 평상시 ON인 NC 버튼이라 래더에서는 NO 접점입니다.
- 자기유지는 시작 접점과 자기 출력 접점(Y0 자신)을 parallel로 묶고 정지 접점을 series로 연결합니다.
- 지연 뒤에도 유지해야 하면 타이머 완료 접점(T0)으로 내부 릴레이(M0)를 자기유지시킵니다.
- 푸시버튼 NC 정지는 NO 접점(평상시 ON이라 정지 시 OFF), 푸시버튼 NO 시작은 NO 접점입니다.
- 한 출력(Y)은 한 렁에서만 구동합니다(같은 Y를 두 렁에서 OUT 하지 않습니다).
- 분석 결과의 assumptions를 지키고, 없는 신호를 만들지 않습니다. Q시리즈 래더·자동 모드만 지원합니다.
- 설명 문장 없이 도구만 호출하고, 안전하다고 단정하지 않습니다.
```

### 수정 에이전트 (지침)
도구는 `getFixInput`, `submitFix` 두 개만 연결해요. 팀장의 연결된 에이전트로 추가하세요. 팀장 지침에는 아래 6번을 더하고, 팀장에게도 이 두 도구를 연결해 주세요. 백엔드는 `FIX_ENABLED=1`일 때만 수정을 시작해요.
```
[팀장 지침에 추가]
6. [수정 시작] job_id=... 를 받으면 수정 에이전트에게 job_id를 넘기고, 수정 에이전트가 submitFix를 호출하면 끝납니다. 수정이 성공했는지는 서버가 정하므로 "고쳤어요"라고 단정하지 않고 결과 state만 전달합니다.

[수정 에이전트 지침]
당신은 MELSEC Q시리즈 PLC 래더 수정 담당입니다. 팀장이 job_id를 넘기면 다음 순서로 일합니다.
1. getFixInput(job_id)으로 fix_request를 읽습니다. 안에는 failed_conditions(고칠 조건과 실패 이유·렁), protected_conditions(이미 통과해서 깨면 안 되는 조건), problems, ir(현재 회로), emergency_stop, io_list, similar_cases(같은 PLC 시리즈에서 검증된 참고 사례)가 있습니다.
2. failed_conditions의 message와 rung_id를 보고 ir에서 원인을 찾아 최소한만 고칩니다. protected_conditions는 반드시 계속 통과해야 합니다.
3. 고친 전체 회로를 submitFix(job_id, ir, reason)로 제출합니다. reason에는 무엇을 왜 고쳤는지 한두 문장만 씁니다. 개인정보나 비밀값은 쓰지 않습니다.
4. ok가 false이면 errors를 읽고 다시 고쳐 제출합니다(서버가 횟수를 세고, 한도를 넘으면 사람 확인으로 넘겨요).

[규칙]
- ir은 설계 에이전트와 같은 IR 모양({"version":1,"rungs":[...]})이며 일부가 아니라 전체 회로를 보냅니다.
- 회로가 바뀌지 않았거나 이전에 통과한 조건이 깨지면 거부됩니다. 비상정지 접점(emergency_stop)과 io_list에 없는 신호는 건드리지 않습니다.
- similar_cases는 참고만 하고 그대로 복사하지 않습니다.
- 성공 여부는 서버가 모든 조건을 다시 모의 실행해서 정합니다. "고쳤다", "안전하다"고 단정하지 않고 설명 문장 없이 도구만 호출합니다.
```

## 수정 단계가 하는 일

- 검증이 실패하면(`FIX_ENABLED=1`) `FIXING`이 되고 백엔드가 팀장에게 "[수정 시작] job_id=..."를 보내요(`runner.py`).
- `getFixInput`: `fix_request`(`plc/fix_request.py`)와 같은 시리즈의 검증된 사례(`plc/error_knowledge.py`)를 돌려줘요.
- `submitFix`: `plc/fix_check.py`가 형식·설계 검사 → 변경 여부 → 전체 재검증 → 이전 통과 조건 유지를 확인해요. 통과하면 새 `design`(고친 회로)과 `fix_applied`(변경 내용) 이벤트를 저장하고 `COMPLETED`예요. 거부되면 `fix_rejected` 이벤트와 이유를 돌려주고 `iteration`이 1 늘어요. `max_iter`(기본 5)에 닿으면 `ESCALATED`예요.
- 수정 에이전트가 제한 시간 안에 응답하지 않으면 `ESCALATED`로 넘어가요.
- 성공한 수정만 오류 사례 DB에 저장해요. 증상·원인·해결 문장은 코드가 정한 틀(조건 종류, 실패 코드, 변경 개수)로만 채우고 자유 입력은 넣지 않아요.

## 설계 단계가 하는 일

설계는 **설계 에이전트(AI)가 회로를 만들고 코드가 검사**하는 구조예요. 문장 해석이나 고정 규칙은 없어요.
- `validateIr`: 저장 없이 검사만(`app/plc/design_check.py` → #63 `validate_ir`, `to_il`). 고칠 점(`errors`)과 IL을 돌려줘요.
- `submitDesign`: 같은 검사를 통과하면 `design` 이벤트로 저장(IR, 실제 사용 I/O, 조건별 설명, 가정·한계, IL). 거부되면 `design_rejected` 이벤트와 `errors`를 돌려주고, 5번 거부되면 `FAILED`예요. 성공하면 서버가 자동 검증(`VERIFYING`)으로 넘어가요. 설계 저장은 안전 승인이 아니에요.
- 코드가 막는 것: IR 형식 오류, 등록되지 않은 신호, 주소 범위·중복 출력, 조건을 만족하는 렁이 없음(covers), 비상정지 누락, Q시리즈·자동 모드 외 설정.
- 코드가 못 막는 것: 회로 논리가 문장의 뜻과 다른 경우(예: 지연 뒤 유지 누락). 화면에 "자동 초안, 사람이 확인" 안내를 띄우고, 이후 검증 단계(#42)에서 다룰 예정이에요.
- 내부 M/T/C 끝값은 매뉴얼 미확인 임시값(M8192/T2048/C1024)이라 `limitations`에 밝혀요.
- 백엔드는 분석이 끝나 DESIGNING이 되면 팀장에게 "[설계 시작] job_id=..."를 보내요(`runner.py`). 정답 회로 예시는 `backend/tests/fixtures/ir_cases.json`이에요.


## 4. 시험

1. 웹 화면에서 프로젝트를 저장하고 "분석 시작"을 눌러요. (에이전트 없이 화면만 보려면 `AGENT_DEMO=1`)
2. 또는 Copilot Studio 테스트 창에 "[작업 시작] project_id=<ID> job_id=<JOB>"처럼 입력 (job은 `POST /projects/<ID>/run`으로 만들어요)
3. 기대 결과: 조건이 `C1, C2…`로 나뉘고, I/O에 없는 신호가 있으면 질문이 나오며, 없으면 `DESIGNING`
4. `GET /projects/<ID>/status`로 단계 기록 확인

## 단계별 연결 현황

| 이슈 | 연결 위치 | 입력 → 출력 (계약: `app/contracts.py`) | 상태 |
|---|---|---|---|
| #41 설계 | 백엔드가 `[설계 시작]`을 보냄 → 설계 에이전트 | `StructuredRequirements` → `Ir` → 검사 통과 시 저장하고 `VERIFYING`으로 이동 | 완료 |
| #42 검증 | `VERIFYING` 상태에서 서버가 자동 실행 | `Ir` → `VerificationResult`. 결과는 `orchestrator.report_verification`으로 | 완료 |
| #43 수정 | `FIXING` 상태 → 수정 에이전트(`getFixInput`/`submitFix`) | `fix_request` → 고친 `Ir` → 서버가 `check_fix`로 재검증 | 완료 |
| #44 파일 생성 | `COMPLETED → GENERATING → DELIVERED` | `Ir` → IL 파일, GX Works 파일은 PoC 확인 후 | 예정 |

분석 결과는 `job_events`의 `requirements` 이벤트(`data`가 `StructuredRequirements`)에 저장돼요. 상태 전이는 `app/agents/orchestrator.py`의 `_move()`만 사용해 주세요.

## 주의
- 입력한 I/O 목록과 조건은 Microsoft 서비스로 전송돼요. 기밀 도면은 조직 정책을 확인한 뒤 사용하세요.
- 에이전트 도구 호출 결과가 틀려도 백엔드가 신호 존재 여부와 비상정지를 다시 점검하지만, 회로 안전은 보장하지 않아요.
