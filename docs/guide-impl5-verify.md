# 구현 5 길잡이: 회로 검증기 (#42)

이 문서는 구현 5 담당자와 담당자의 Copilot이 같이 읽는 길잡이예요. 이슈 #42의 완료 조건이 기준이고, 이 문서는 "어떻게 시작하고 어디까지 하는지"를 알려 줘요.

## 1. 한 줄 목표
**설계 에이전트가 만든 회로(`Ir`)가 사용자의 조건(`conditions`)대로 동작하는지 파이썬 코드로 판정해 `VerificationResult`를 돌려주는 함수를 만든다.**

```
분석 결과 StructuredRequirements ─┐
                                  ├→ verify() → VerificationResult(passed, errors, warnings)
설계 결과 Ir ─────────────────────┘
```

- 지금 #41(설계)은 "형식이 맞는가"만 검사해요 (신호 존재, 주소 범위, 비상정지, 조건 반영 여부). **회로가 실제로 그렇게 동작하는지는 아무도 확인하지 않아요.** 그 빈자리를 채우는 게 구현 5예요.
- 예: 지연 뒤 유지가 빠진 회로는 형식 검사를 통과해요. 구현 5가 이런 회로를 `FAIL`로 잡아야 해요.

## 2. 반드시 지킬 약속
1. **AI가 아니라 일반 코드로 판정해요.** 회로 평가, 타이머 계산, 통과 판정은 파이썬과 테스트로 만들어요. 같은 입력이면 항상 같은 결과가 나와야 해요.
2. **계약(`backend/app/contracts.py`)을 바꾸지 않아요.** 입력은 `StructuredRequirements`와 `Ir`, 출력은 `VerificationResult`예요. 꼭 바꿔야 하면 PR 제목에 `[계약 변경]`을 붙이고 이유를 설명해요.
3. **다른 담당자의 파일을 고치지 않아요.** 특히 `design_check.py`, `rules.py`, `to_il.py`(#41), `orchestrator.py`, `mcp_api.py`(팀장 연결 담당), Copilot Studio 지침은 읽기만 해요.
4. **연결은 하지 않아요.** 함수와 테스트까지가 범위예요. 에이전트·MCP 도구·상태 머신(`VERIFYING`) 연결은 팀장이 해요.
5. **통과를 쉽게 주지 않아요.** `must_pass=true` 조건이 하나라도 실패하거나, 검사할 수 없으면 전체 `passed=False`예요. 검사하지 못한 조건을 통과로 세지 않아요.
6. **모의 실행이 통과해도 안전을 보장하지 않아요.** 보고서와 문서에 이 문구를 유지해요.

## 3. 먼저 읽을 것 (순서대로)
1. 이슈 #42 (완료 조건)
2. `backend/app/contracts.py` — `Ir`, `Rung`, `Condition`, `VerificationResult`, `VerificationIssue`
3. `backend/app/plc/rules.py`, `design_check.py` — 이미 있는 검사. **같은 검사를 다시 만들지 않아요.** (이중 출력, 없는 신호, 주소 범위는 이미 있어요.)
4. `backend/tests/fixtures/*.json` — `self_hold`, `on_delay`, `estop_interlock` 예시 (`requirements`, `ir`, `verification` 세트)
5. `backend/tests/test_design_agent.py` — 테스트 작성 방식 참고

## 4. 만들 것 (이 순서로, 한 번에 하나씩)

### 4-1. 스캔 시뮬레이터 `backend/app/plc/sim.py`
- 상태는 `{디바이스: bool 또는 int}` 딕셔너리예요. 타이머는 스캔 시간(기본 10ms)을 누적해서 계산해요.
- 한 스캔은 **입력 반영 → 렁을 위에서 아래로 평가 → 출력 반영**이에요.
- 접점 `NO/NC`, 직렬 `AND`, 병렬 `OR`, 출력 `OUT/SET/RST/TON/CTU`를 평가해요.
- `run(ir, steps)`를 만들어요. `steps` 예시: `[{"t_ms":0,"set":{"X1":1}}, {"t_ms":100,"set":{"X1":0}}]`
- 결과는 시간별 디바이스 상태 기록(trace)이에요.
- **주의**: 입력 신호는 `X1` 같은 주소나 `START` 같은 이름으로 올 수 있어요. io_list로 주소로 통일해요. 평상시 ON인 NC 버튼(비상정지 등)은 래더에서 NO 접점이라는 점을 시나리오에서 헷갈리지 않게 해요.

### 4-2. 시나리오 `backend/tests/fixtures/scenarios/` (먼저 손으로 만들기)
조건 하나당 입력 순서와 기대값을 JSON으로 적어요.
```json
{"condition_id": "C1",
 "steps": [{"t_ms": 0, "set": {"X1": 1}}, {"t_ms": 50, "set": {"X1": 0}}],
 "expect": [{"t_ms": 100, "dev": "Y0", "value": 1}]}
```
- 먼저 **손으로 쓴 시나리오**로 시작해요. AI가 시나리오를 만드는 일은 이 단계가 다 통과한 뒤에 하고, 그때도 스키마 검증을 통과한 것만 받아요.
- 필수 시나리오 4개: 자기유지(START 뗀 뒤에도 유지, STOP/EMG에서 꺼짐), 타이머 지연(3초 전에는 OFF, 후에는 ON), 비상정지 인터록(EMG에서 모든 출력 OFF), 정상 동작 중 오동작 없음.

### 4-3. 판정 함수 `backend/app/plc/verify.py`
```python
def verify(req: StructuredRequirements, ir: Ir, scenarios: list[dict]) -> VerificationResult: ...
```
- 모든 시나리오를 실행해 기대값과 비교해요.
- 실패하면 `VerificationIssue(code, message, rung_id, condition_id)`를 `errors`에 넣어요. `message`에 **기대한 값, 실제 값, 실패 시각**을 한국어로 적어요. (계약에 전용 필드가 없으니 message에 적어요. 필드가 꼭 필요하면 `[계약 변경]`으로 먼저 논의해요.)
- 코드 이름은 `UNMET_CONDITION`(조건 불만족), `UNVERIFIABLE`(검사 불가)처럼 기존 이름 방식을 따라요.
- `must_pass=true`인 조건에 시나리오가 없으면 `UNVERIFIABLE` 오류예요. `must_pass=false` 조건은 `warnings`로만 남겨요.

### 4-4. 정적 검사 보강 `backend/app/plc/static_check.py` (필요할 때만)
`rules.py`에 없는 것만 추가해요. 예: 타이머 preset 누락·0, 입력(X)을 코일로 사용. 이미 있는지 먼저 확인해요.

## 5. 테스트 (먼저 쓰고 시작해요)
`backend/tests/test_sim.py`, `test_verify.py`에 만들어요.
- [ ] 정상 자기유지 회로: START → ON 유지, EMG → OFF 시나리오가 PASS
- [ ] **일부러 고장 낸 회로**: b접점(정지) 누락 → 인터록 조건 FAIL, 실패 시각이 message에 있음
- [ ] 정상 타이머 5초 지연 ON → PASS, 고장(타이머 누락) → FAIL
- [ ] `must_pass` 조건에 시나리오가 없으면 `passed=False`
- [ ] `VerificationResult`는 `passed`와 `errors`가 서로 맞아야 해요 (계약의 검사)
- 기존 테스트(`cd backend; pytest -q`)가 모두 통과해야 해요.

## 6. 하지 않는 것
- Copilot Studio 에이전트 지침 수정, MCP 도구 추가, `orchestrator` 상태 전이 변경
- IR 형식·`VerificationResult` 변경 (필요하면 먼저 팀장에게 알려요)
- GX Simulator 확인, GX Works 파일 생성 (#44)
- 회로를 직접 고치는 일 (#43 수정 담당)
- 관련 없는 리팩터링, 새 의존성 추가

## 7. PR 올리기 전 체크
- [ ] 브랜치 이름은 `feat/42-verify`처럼 이슈 번호를 넣어요. `main`에서 직접 작업하지 않아요.
- [ ] 이슈 #42의 완료 조건을 하나씩 확인했어요. 확인하지 못한 항목은 PR에 이유를 적어요.
- [ ] 테스트 실행 결과(통과/실패 개수)를 PR에 붙여요. 실행하지 않은 것을 통과로 쓰지 않아요.
- [ ] 이 PR이 **부분 구현**이면 `Closes #42` 대신 `Refs #42`를 써요.
- [ ] 비밀번호·API 키가 없어요.
- [ ] PR을 만든 뒤 앱에서 `student-reviewer`를 선택해 리뷰를 요청해요. 팀장 승인 전에는 병합하지 않아요.

## 8. 막히면
- 계약이나 `Ir` 형식이 모호하면 팀장에게 먼저 물어요. 추측해서 바꾸지 않아요.
- 설계 쪽 오류처럼 보이면(예: `Ir`가 이상함) 고치지 말고 PR이나 이슈에 사례를 적어 알려요.
- 시뮬레이터 정확도(스캔 시간, 타이머 해석)는 개발용 모의 실행 수준이면 충분해요. 실제 PLC와 100% 같을 필요는 없어요.
