# Copilot Studio 에이전트 연결 가이드

역할 나누기
- **Copilot Studio**: 팀장·분석 에이전트의 판단(조건 해석, 질문 만들기)
- **백엔드(이 저장소)**: 입력 보관, 신호·비상정지 점검, 상태 머신(`jobs`), 기록(`job_events`)

```
사용자 → (웹 화면) → 백엔드에 프로젝트 저장
팀장 에이전트 → startJob → 분석 에이전트 → submitRequirements → 백엔드 점검
  → 질문이 있으면 NEEDS_INPUT (사용자에게 질문) / 없으면 DESIGNING
```

## 1. 백엔드 준비

1. 서버 환경변수 `AGENT_API_KEY`에 길고 무작위인 값을 넣고 백엔드를 다시 켜요. 키는 저장소에 올리지 마세요.
2. Copilot Studio는 인터넷에서 백엔드에 접근해야 해요. `localhost`는 안 돼요.
   - 임시: Dev Tunnel 등으로 8000 포트를 공개 (`devtunnel host -p 8000 --allow-anonymous` — 익명 접근을 열어도 `/agent/*`는 API 키가 막아 줘요)
   - 정식: 이슈 #45의 배포 주소
3. `https://<공개주소>/agent-spec.json`이 열리는지 확인해요.

## 2. 도구(REST API) 추가

Copilot Studio → 에이전트 → **도구 → 도구 추가 → REST API** → `agent-spec.json` 가져오기.
- 인증: **API 키**, 위치 **헤더**, 이름 `X-API-Key`, 값은 `AGENT_API_KEY`
- 가져오면 도구 4개가 생겨요: `startJob`, `getStatus`, `submitRequirements`, `reportVerification`

## 3. 에이전트 만들기

### 팀장 에이전트 (지침)
```
당신은 MELSEC PLC 회로 설계 팀의 팀장입니다. 사용자가 프로젝트 ID를 주면 다음 순서로 일합니다.
1. startJob 도구로 작업을 시작하고, 돌려받은 project 내용을 분석 에이전트에게 넘깁니다.
2. 분석 에이전트의 결과를 submitRequirements 도구로 제출합니다. job_id는 startJob 결과의 job.job_id입니다.
3. 결과 state가 NEEDS_INPUT이면 questions를 사용자에게 그대로 묻고, 답을 받으면 1부터 다시 합니다.
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
- 모호한 조건(시간, 순서, 정지 방식 등)은 임의로 정하지 말고 questions에 적습니다. 어쩔 수 없이 가정하면 assumptions에 적습니다.
- 비상정지(emergency_stop)가 사용 설정이면 "모든 출력 OFF" 조건을 safety로 포함합니다.
- 설명 문장 없이 JSON만 출력합니다.
```

팀장 에이전트의 **연결된 에이전트**로 분석 에이전트를 추가하고, 도구 4개는 팀장에게 연결해요.

## 4. 시험

1. 웹 화면에서 프로젝트를 저장하고 프로젝트 ID를 확인 (`GET /projects`)
2. Copilot Studio 테스트 창에 "프로젝트 `<ID>` 분석해줘" 입력
3. 기대 결과: 조건이 `C1, C2…`로 나뉘고, I/O에 없는 신호가 있으면 질문이 나오며, 없으면 `DESIGNING`
4. `GET /projects/<ID>/status`로 단계 기록 확인

## 주의
- 입력한 I/O 목록과 조건은 Microsoft 서비스로 전송돼요. 기밀 도면은 조직 정책을 확인한 뒤 사용하세요.
- 에이전트 도구 호출 결과가 틀려도 백엔드가 신호 존재 여부와 비상정지를 다시 점검하지만, 회로 안전은 보장하지 않아요.
