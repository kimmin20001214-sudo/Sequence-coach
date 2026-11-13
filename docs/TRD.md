# Sequence Coach 기술 요구사항 정의서 (TRD)

## 1. 문서 정보

| 항목 | 내용 |
| --- | --- |
| 제품명 | Sequence Coach (MELSEC PLC 회로 설계 지원) |
| 문서 유형 | 기술 요구사항 정의서 (TRD) |
| 버전 | v2 (구현 현황 반영, 2026-11-11) |
| 관련 문서 | [PRD](PRD.md), [Copilot Studio 연결 가이드](copilot-studio.md), [backend/README](../backend/README.md) |
| 구현 상태 | 입력·분석·설계·검증·수정·결과·모의 실행 구현됨. IL 파일(#44)과 통합·배포(#45)는 예정 |

## 2. 기술 원칙

- **AI 판단과 정확한 계산을 분리한다.** AI(Copilot Studio)는 조건 분석·회로 작성·수정만 하고, 규칙 검사·시험 대본 생성·시뮬레이션·IL 변환은 일반 코드와 테스트로 처리한다.
- 에이전트끼리는 Pydantic 계약(`backend/app/contracts.py`)으로만 데이터를 주고받는다. 계약을 바꾸면 PR 제목에 `[계약 변경]`을 붙인다.
- 상태 전이는 `orchestrator._move()`만 사용한다. 실패·시간 초과·빈 응답은 성공으로 바꾸지 않는다.
- 검증하지 않은 결과(실기 동작, GX Works 호환)는 성공으로 표시하지 않는다.
- 화면 검증(`frontend/src/validate.ts`)과 서버 검증(`backend/app/validation.py`)은 같은 규칙을 유지한다.

## 3. 아키텍처

```text
브라우저 (React + Vite + TypeScript)
   |  /api/*  (개발: Vite 프록시, 배포: 같은 서버)
   v
FastAPI 서버 (backend/app)
   |-- 입력·메타·템플릿 API, 사전 점검(preflight)
   |-- run_api: 작업 시작 /projects/{id}/run
   |-- agents/runner + orchestrator: 작업 상태 머신, 에이전트 호출·대기
   |-- /mcp (MCP 도구) + /agent/* (REST, X-API-Key): 에이전트가 쓰는 도구
   |-- plc/: 규칙 검사, IR→IL, 정적 검사, 스캔 시뮬레이터, 시험 틀(checks), 수정 요청
   '-- SQLite: 프로젝트, 작업(jobs), 작업 이벤트(job_events), 템플릿

Microsoft Copilot Studio 에이전트: 팀장 / 분석 / 설계 / 수정
   (Direct Line으로 백엔드가 호출, 에이전트는 MCP 도구로 결과를 제출)
```

흐름: `조건 입력 → 사전 점검 → 분석 → 설계 → 자동 검증 ⇄ 수정 → 결과·모의 실행`.

**v1과의 차이**: v1의 안전 검토 게이트(에이전트)와 회로 검증 에이전트는 코드 검증(`plc/`)으로 대체됐다. v1의 `SimulatorAdapter`·`MelsecExportAdapter` 추상화는 만들지 않았고, 시뮬레이터는 자체 구현(백엔드 파이썬 + 프런트 `sim/engine.ts`)이다.

## 4. 작업 상태 머신

`backend/app/contracts.py`의 `JOB_TRANSITIONS`가 기준이다.

```text
INPUT_VALIDATED -> ANALYZING -> DESIGNING -> VERIFYING -> COMPLETED -> GENERATING -> DELIVERED
                      |             |            |  ^
                      |             |            v  |
                      |             |          FIXING
                      |             |            |
                      v             v            v
                 NEEDS_INPUT      FAILED      ESCALATED   (수정 횟수가 max_iter, 기본 5에 도달)
```

- `NEEDS_INPUT`: 분석이 사용자 확인을 요구. 질문은 최대 3개(`MAX_QUESTIONS`). 답하면 화면이 새 작업을 `answers`와 함께 시작한다.
- `COMPLETED → GENERATING → DELIVERED`는 #44 파일 생성에서 사용 예정.
- 각 전이는 `job_events`에 기록되어(`state`, `kind`, `data`, `created_at`) 화면의 단계별 경과 시간 계산에 쓰인다.

## 5. 계약(데이터 형식)

| 계약 | 설명 |
| --- | --- |
| `StructuredRequirements` | 분석 결과. `Condition`(ID, 유형 `sequence/interlock/timing/safety/alarm`, `Check`), `TimerSpec`, `CounterSpec` 포함 |
| `Check` | 시험 틀 이름(`self_hold`, `stop_priority`, `on_delay`, `timed_on`, `interlock`, `and_enable`, `or_enable`, `indicator`, `set_reset`, `custom`)과 신호 이름. 시험 대본은 코드가 생성 |
| `Ir` | 회로. 접점 `Contact`(NO/NC), 직렬 `Series`, 병렬 `Parallel`, 출력 `Output`(OUT, SET, RST, TON, CTU), `Rung` |
| `VerificationResult` / `VerificationIssue` | 검증 결과와 문제(예: `DOUBLE_COIL`) |

## 6. 백엔드 구성

| 영역 | 파일 | 역할 |
| --- | --- | --- |
| 입력 | `main.py`, `validation.py`, `spec.py`, `data/*.json` | PLC 기준 데이터(`plc_spec.json`, `instructions.json`), 검증, 프로젝트·템플릿 저장 |
| 사전 점검 | `preflight.py`, `run_api.py` | 실행 전 차단: Q시리즈·래더·호환 CPU/소프트웨어 아님, 타이머 단위가 100ms 아님, 조건의 시간이 100ms 배수가 아니거나 K32767 초과. 차단 시 HTTP 422 + 한국어 사유 목록 |
| 에이전트 | `agents/runner.py`, `orchestrator.py`, `analyzer.py`, `schemas.py` | 작업 실행·상태 기록·질문 정리. 제한 시간 `COPILOT_TIMEOUT_SECONDS`(기본 180초) |
| 에이전트 도구 | `mcp_api.py`, `agent_api.py` | MCP: `getJob`, `submitRequirements`, `getDesignInput`, `validateIr`, `submitDesign`, `getFixInput`, `submitFix`, `getStatus`, `reportVerification`, `startJob`. REST `/agent/*`는 `AGENT_API_KEY` 필요 |
| 회로 규칙 | `plc/rules.py`, `design_check.py`, `to_il.py` | IR 사전 검사(비상정지 인터록 포함), 신호표, IR→IL 변환 |
| 검증 | `plc/verify.py`, `static_check.py`, `sim.py`, `scenario.py`, `checks.py`, `auto_check.py` | 정적 검사, 스캔 시뮬레이션(10ms), 조건별 시험, 자동 안전 탐색 |
| 수정 | `plc/fix_request.py`, `fix_check.py`, `ir_diff.py`, `error_knowledge.py` | 실패 원인을 수정 에이전트에 전달, 고친 IR을 서버가 재검증, 변경 비교 |
| 저장 | `db.py` | 개발용 SQLite. 배포 시 PostgreSQL 등으로 교체 필요 |

주요 API: `GET /health`, `/meta*`, `POST /validate`, `POST /projects`, `GET /projects[/{id}]`, `GET /projects/{id}/status`, `POST /projects/{id}/run`(202), `/templates`, `/agent-mode`, `/agent-spec.json`.

## 7. 프런트엔드 구성

`frontend/src`: 5단계 마법사(기본 설정 → 동작 조건 → 설계 요청 → 검증 결과 → 모의 실행).

| 파일 | 역할 |
| --- | --- |
| `App.tsx`, `SettingsStep.tsx`, `ConditionsStep.tsx`, `TemplatesCard.tsx`, `csv.ts`, `validate.ts`, `spec.ts` | 입력 화면, CSV 가져오기, 템플릿, 검증 |
| `RunStep.tsx`, `api.ts` | 실행·상태 조회(2초 폴링), 단계별·총 경과 시간, 사전 점검 422 표시 |
| `Result.tsx`, `Criteria.tsx` | 결과 요약, 조건별 결과, "검증 신뢰도 낮음" 배지, 검증 기준 팝업, 설계 보기 |
| `sim/` (`engine.ts`, `PlcSimulator.tsx`, `LadderView.tsx`) | 웹 모의 실행. 시작 버튼을 눌러야 재생 |
| `simulator.html` | 시뮬레이터 단독 데모 페이지 |

## 8. 검증 로직

- **시험 틀(check)**: 분석 에이전트는 틀 이름과 신호 이름만 고르고, 시험 입력 대본은 `scenario.py`/`checks.py`가 만든다. 틀로 표현할 수 없는 조건은 `custom`이며, 결과에 "검증 신뢰도 낮음"과 이유를 붙인다.
- **자동 안전 탐색**: 시나리오가 부족해도 거짓 통과가 나지 않도록 `auto_check.py`가 고정 seed로 입력을 흔들어 본다. 아무것도 누르지 않았는데 출력이 켜짐, 정지·비상정지를 누른 채 출력이 켜짐, 어떤 입력으로도 켜지지 않는 출력, 조건이 말한 신호를 시험이 다루지 않음(경고)을 찾는다.
- **판정**: 통과·실패·실행 불가를 구분한다. 수정 반복이 최대 횟수에 도달하면 `ESCALATED`로 끝낸다.
- **알려진 한계**: 시뮬레이터는 10ms 고정 스캔이며 PLC 설정을 반영하지 않는다. TOF 출력이 없어 오프딜레이는 TON+자기유지 `custom` 시험으로 확인한다.

## 9. 테스트와 CI

- 백엔드: `cd backend; pytest -q` (현재 340개 통과, 20개 테스트 파일). 설계·검증·수정·사전 점검·에이전트 흐름·MCP를 포함한다.
- 프런트: `npm run lint`, `npm run build`. 린트에는 `sim/demo.tsx`의 기존 경고 1건이 있다.
- CI: `.github/workflows/ci.yml`. PR 리뷰: 앱의 `student-reviewer` 에이전트.
- 실제 에이전트 시험은 Studio 연결이 필요해 로컬 스크립트로 한다. 오프딜레이 회로는 실제 에이전트로 완료(약 88초)와 IL 출력까지 확인했다.

## 10. 설정과 보안

| 환경변수 | 용도 |
| --- | --- |
| `AGENT_API_KEY` | `/agent/*` 인증. 없으면 닫힘 |
| `AGENT_DEMO=1` | 에이전트 없이 가짜 분석으로 화면 시험(`start-demo.bat`) |
| `COPILOT_TIMEOUT_SECONDS` | 에이전트 응답 제한(기본 180) |
| `DATABASE_PATH` | SQLite 경로(기본 `data.sqlite3`) |
| `PORT` | 배포 포트(Render가 지정) |

- 비밀값(API 키, Direct Line 암호)은 소스·로그·이슈에 넣지 않는다. 개발 중 노출된 값은 **배포 전 교체**해야 한다.
- 사용자 입력은 Microsoft 서비스(Copilot Studio)로 전송된다. 기밀 도면은 조직 정책 확인 후 사용한다.
- 에이전트 결과는 신뢰하지 않고 백엔드가 항상 다시 검사한다(신호 존재, 비상정지, IR 규칙).
- 인증·사용자 권한·데이터 보존 정책은 아직 없다(단일 팀 개발용). 배포 전에 결정한다.

## 11. 배포

루트 `Dockerfile` + `render.yaml`: FastAPI 서버 1개가 프런트 빌드 결과와 `/api/*`를 함께 제공한다(상태 확인 `/api/health`). 로컬 실행은 `start.bat`(실제 에이전트), `start-demo.bat`(데모). Render 무료 플랜은 슬립 후 첫 응답이 느리고 디스크가 영구 저장이 아니다.

## 12. 남은 기술 과제

| 항목 | 설명 |
| --- | --- |
| #44 GX Works 파일 | 결과 화면에서 GX Works2용 CSV 받기(PR #103). 자기유지·타이머 회로를 GX Works2 체험판(Q03UD)에서 읽어 래더 표시를 확인. GX Simulator2 확인은 사용자 재시험 대기 중(정지·비상정지는 NO 버튼 + b접점으로 설계해 먼저 ON으로 둘 필요가 없어요. 디자인 에이전트 지침을 새로 붙여 넣어야 해요). CTU·SET/RST·분기 명령·다른 CPU는 미확인. 영상은 만들지 않음. 옛 PoC 브랜치 `feat/44-gxworks`(PR #64)는 참고용 |
| #45 통합·배포 | Render 배포, 비밀값 교체, DB 교체 검토 |
| `off_delay` 시험 틀 | 오프딜레이를 `custom` 대신 전용 틀로 검증 |
| 시뮬레이터 | PLC 설정(CPU 성능 등) 반영 |
| 실패 화면 | 실패 사유를 마크다운으로 알기 쉽게 표시 |
| 응답 속도 | 분석·설계 지침 축약, 빠른 모델은 Studio에서 품질 확인 후 판단. 분석 생략은 하지 않음 |
| 정리 | 중복 이슈 #10~#17, 테스트 프로젝트 데이터 |
