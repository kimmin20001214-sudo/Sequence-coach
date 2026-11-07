# Backend (FastAPI)

PLC 기준 데이터(`/meta`)와 입력 검증·저장(`/projects`)을 제공합니다. 화면(frontend)은 이 서버에서 선택지를 받아 그립니다.

## 실행 (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

화면과 함께 쓰려면 다른 터미널에서 `cd frontend; npm run dev` 를 실행하세요. 화면의 `/api/*` 요청은 개발 서버가 8000 포트로 전달합니다.

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/health` | 상태 확인 |
| GET | `/meta` | 시리즈·CPU·선택지·안전 고지 전체 (화면이 사용) |
| GET | `/meta/series`, `/meta/cpus?series=`, `/meta/instructions?series=` | 부분 조회 |
| POST | `/validate` | 저장 없이 검증. `{ok, fields, io}` |
| POST | `/projects` | 검증 후 저장. 오류면 422 + `{fields, io}` |
| GET | `/projects`, `/projects/{id}` | 목록·상세 |

## 데이터

- `app/data/plc_spec.json` : 시리즈/CPU/점수/표기법. `verified: false` 는 **매뉴얼 확인 전 값**입니다.
- `app/data/instructions.json` : MVP 래더 명령어.
- 저장소는 개발용 SQLite(`DATABASE_PATH`, 기본 `data.sqlite3`)입니다. 배포 시 PostgreSQL로 교체합니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## 에이전트 API (구현 3)
에이전트의 AI 판단은 Copilot Studio에서 하고, 백엔드는 검증·상태 기록을 맡아요. 자세한 연결 방법은 [docs/copilot-studio.md](../docs/copilot-studio.md)를 보세요.
- `/agent/*` API는 `X-API-Key` 헤더가 필요해요. 서버 환경변수 `AGENT_API_KEY`가 없으면 닫혀 있어요.
- `GET /agent-spec.json`: Copilot Studio에 가져올 OpenAPI 문서
- `GET /projects/{id}/status`: 화면용 상태 조회

## IR 사전 검사와 명령어 초안 (구현 4의 일부)

공용 `app/contracts.py`의 `Ir`를 그대로 사용해요. 서버·화면·Copilot Studio 연결 없이
파이썬에서 호출하는 함수이며, 요구사항에서 회로를 새로 설계하거나 저장하지는 않아요.
`backend` 폴더에서 다음처럼 기존 타이머 예시를 읽을 수 있어요.

```python
import json
from pathlib import Path
from app.contracts import Ir, StructuredRequirements
from app.plc.rules import validate_ir
from app.plc.to_il import IrConversionError, to_il

data = json.loads(Path("tests/fixtures/on_delay.json").read_text(encoding="utf-8"))
req = StructuredRequirements.model_validate(data["requirements"])
ir = Ir.model_validate(data["ir"])
# 예시에서 T0만 허용: 실제 CPU의 하드웨어 상한을 뜻하지 않아요.
limits = {"T": 1}
result = validate_ir(ir, req.plc_config, req.io_list, internal_limits=limits)
print(result.model_dump())  # passed/errors/warnings. 안전 검증 완료를 뜻하지 않아요.
if result.passed:
    try:
        print(to_il(ir, req.plc_config, req.io_list, internal_limits=limits))
    except IrConversionError as exc:
        print(exc.result.model_dump())
```

- 지원: Q시리즈 + 호환 CPU + `ladder` + GX Works2/GX Developer. X/Y는 16진수,
  M/T/C는 10진수예요. I/O 이름은 공백·대소문자를 정리하여 주소로 바꿔요.
  중복 주소·모호한 이름·미등록 I/O·설정 점수 밖 I/O는 거부해요.
- 내부 주소는 `PlcConfig.device_rule`의 시작 번호 이상, 호출자가 전달한
  `internal_limits`의 끝값 **미만**이어야 해요. 사용한 종류의 끝값이 없으면 오류예요.
  기준 데이터에 내부 주소 상한이 없으므로 CPU 한계를 임의로 만들지 않아요.
  호출자가 매뉴얼과 프로젝트 할당을 확인하여 이 범위를 지정해야 해요.
- 중첩 AND/OR는 `ANB`/`ORB`, NO/NC는 `LD`/`LDI` 등으로 변환해요.
  여러 출력은 `MPS`/`MRD`/`MPP`로 조건을 보존하고 마지막에 `END`를 붙여요.
  생성되는 모든 명령어는 `app/data/instructions.json`의 시리즈 허용목록으로 검사해요.
- `OUT`/`SET`/`RST`는 Y/M 비트만 지원해요. `TON T…`는 `OUT T… K…`,
  `CTU C…`는 `OUT C… K…`로 변환해요. 타이머는 **100ms 단위의 초안만**
  지원하며 설정시간을 정확히 나눌 수 있어야 해요(반올림 없음).
  타이머·카운터 상수는 보수적인 초안 범위 `K1`~`K32767`만 허용해요.
  10ms·1ms 설정, D 워드 접점·출력, T/C의 일반 코일·SET/RST는 미지원 오류예요.
- 원본 IR은 바꾸지 않아요. 변환 실패는 부분 명령어 대신 `IrConversionError.result`로
  공용 `VerificationResult` 오류를 제공해요. JSON 형식 오류는 먼저
  `Ir.model_validate`에서 `ValidationError`로 거부해요.
- 기존 예시 3개를 재사용하며 `tests/fixtures/expected_il.json`은 기대 명령어만 담아요.
  자기유지 예시의 정지 버튼 X2는 평상시 ON이라 `AND X2`가 맞아요.
  이슈의 별도 `ANI X0` 예시는 정지 신호가 켜지면 정지하는 경우이며 테스트로 구분해요.

이 검사는 #42의 이중 코일·스캔·비상정지 시 모든 출력 OFF 검증을 대신하지 않아요.
기존 비상정지 예시도 변환 결과만 확인하며 안전한 회로라고 판정하지 않아요.
CPU 점수의 `verified: false`는 경고로 남겨요. 타이머 시간 기준·내부 주소·명령어의
실제 CPU/펌웨어 적합성, 블록 스택 깊이와 GX Works 열기·컴파일은 미검증이에요.
**실제 설비 적용 전 전문가 확인이 필요해요.** PLC 전송·파일 생성은 제공하지 않아요.

## 회로 동작 판정 함수 (구현 5)

`app.plc.verify.verify(req, ir, scenarios)`는 기존 공통 계약의
`StructuredRequirements`, `Ir`와 손으로 작성한 시나리오 목록을 받아
`VerificationResult(passed, errors, warnings)`를 반환해요.
AI·에이전트가 아니라 일반 Python 코드로 판정해요.
에이전트·MCP·상태 머신·API·DB·화면에는 연결하지 않았어요.
자연어 조건에서 시나리오를 자동 생성하거나 회로를 수정하지도 않아요.

검사 순서는 기존 `rules.validate_ir` → 추가 이중 출력 검사 → 시나리오 모의 실행이에요.
명령어·주소·입력 코일·타이머 설정 검사는 기존 계약과 규칙을 재사용해요.
`static_check.check_double_outputs`는 같은 주소의 OUT/TON/CTU 중복만 보강하고,
SET/RST 쌍은 렁 순서대로 실행하도록 허용해요.
사전 오류가 있으면 동작을 실행하지 않아요.

필수 조건은 시나리오 하나라도 실패·검사 불가·누락이면 `passed=False`예요.
필수 조건이 아예 없거나 조건 ID가 비어 있거나 중복돼도 실패해요.
모르는 조건 ID 또는 조건을 식별할 수 없는 시나리오도 무시하지 않아요.
선택 조건의 실패·누락·검사 불가는 `warnings`에 남겨요.
통과한 조건도 `CONDITION_PASSED`로 `warnings`에 기록해요.
공통 계약에 조건별 성공 전용 필드가 없으므로 이 항목은 경고가 아닌 결과 안내예요.
`UNMET_CONDITION`에는 조건 ID, 출력 렁 ID, 기대값·실제값·모의 실패 시각(ms)이 있어요.
`UNVERIFIABLE`은 실행할 수 없었던 이유를 설명하며, 미실행을 통과로 세지 않아요.

### 자동 안전 탐색 (시나리오 보강)

손으로 쓴 시나리오가 부족해도 거짓 통과가 나지 않도록 `plc/auto_check.py`가
입력을 자동으로 흔들어 봐요(고정 seed, 결과 항상 동일).
- `AUTO_SPONTANEOUS_START`: 아무것도 누르지 않았는데 출력이 켜짐 → 실패
- `AUTO_STOP_PRIORITY`: 정지·비상정지를 누른 채 출력이 켜짐 → 비상정지는 실패, 일반 정지는 경고
- `AUTO_UNREACHABLE_OUTPUT`: 어떤 입력으로도 켜지지 않는 출력 → 필수 조건과 관련되면 실패, 아니면 경고
- `COVERAGE_GAP`(경고): 조건이 말한 신호를 시나리오가 다루지 않음
램프·경보류 출력은 정지 검사에서 제외해요.

### 모의 실행 규칙과 지원 범위

- Q시리즈 래더의 `NO/NC`, `AND/OR`, `OUT/SET/RST/TON/CTU`를 지원해요.
  ST·다른 시리즈·잘못된 주소 등은 기존 사전 규칙에서 거부해요.
- `sim.run(ir, steps, io_list=req.io_list, until_ms=100)`는 기본 10ms 간격으로
  `{t_ms, state, timers, counters}` 기록 목록을 반환해요.
  `until_ms`를 생략하면 마지막 입력 시각까지(입력이 없으면 0ms) 실행해요.
  판정 함수는 마지막 입력·기대 시각까지 실행해요.
- 한 스캔은 입력 반영 → 위에서 아래로 렁 실행 → 종료 상태 기록 순서예요.
  앞 렁의 출력은 같은 스캔의 다음 렁에서 즉시 읽어요.
  한 렁의 여러 출력은 동일한 논리 평가 결과를 사용해요.
- TON은 최초 참 스캔을 경과 0ms로 하고, 참 상태가 유지되는 동안 시간을 누적해요.
  `preset_ms` 이상인 첫 스캔에 완료 접점이 켜지고, 입력 OFF 시 시간과 접점을 초기화해요.
  CTU는 OFF→ON마다 한 번 증가하고 입력 OFF에도 누적값을 유지해요.
  T/C의 `state`는 완료 접점(bool), `timers`는 경과 ms, `counters`는 누적 횟수예요.
  SET은 참일 때 유지 ON, RST는 참일 때 OFF이며 같은 스캔에서는 나중 렁이 우선해요.
  현재 사전 규칙은 T/C를 RST 대상으로 허용하지 않으므로 T/C 리셋 명령은 지원하지 않아요.
- 각 시나리오는 전부 OFF·시간/횟수 0에서 독립적으로 시작해요.
  NC 버튼이라고 자동으로 입력을 ON 하지 않아요. 예시 STOP/EMG는 평상시 1,
  눌렀을 때 0이며 래더에서 **NO 접점**으로 읽어요.
  조건을 평가하는 래더 NC 접점과 실제 NC 버튼의 신호값을 구분해요.
- 입력은 주소 또는 등록 I/O 이름으로 쓰며 공백·대소문자를 정리하고 주소로 통일해요.
  입력 시퀀스는 등록 X 신호의 0/1만 변경할 수 있어요.
  입력 시각은 중복 없는 오름차순 스캔 시각이어야 하고, 기대 시각도 스캔 간격 배수예요.
  기대값은 해당 시각의 스캔 종료 상태와 비교해요.
  오류는 명시적으로 보고하며 최대 100,000 스캔을 넘기는 시나리오는 검사 불가예요.

`verify(..., internal_limits={"T": 1})`처럼 내부 주소 끝값(미포함)을 명시할 수 있어요.
생략하면 기존 설계 단계와 같은 임시 범위(M8192/T2048/C1024)를 재사용하고 경고해요.
이것은 매뉴얼 검증된 CPU 상한이 아니에요. CPU의 `verified: false`도 경고로 남겨요.
모의 실행의 시간·카운터 동작은 실제 CPU·펌웨어 동작과 같다고 보증하지 않아요.

### 학생이 정상·고장 보고서 열기

`tests/fixtures/scenarios/`에 자기유지·3초/5초 지연·비상정지 인터록·정상 운전 예시가 있어요.
각 파일의 `fixture`는 `ir_cases.json`의 예시를 가리켜요.
5초 예시는 `timer_preset_ms`를 요구사항과 IR에 함께 적용하는 테스트용 변형이에요.
실제 `verify()`에는 이 포장 데이터가 아닌 `scenarios` 목록만 전달해요.

`backend`에서 가상환경 Python으로 아래 코드를 실행하면 보고서 두 개를 저장해요.

```python
import json
from pathlib import Path
from app.contracts import Ir, StructuredRequirements
from app.plc.verify import verify

fixtures = Path("tests/fixtures")
case = json.loads((fixtures / "ir_cases.json").read_text(encoding="utf-8"))["self_hold"]
req = StructuredRequirements.model_validate(case["requirements"])
ir = Ir.model_validate(case["ir"])
scenarios = json.loads(
    (fixtures / "scenarios/self_hold.json").read_text(encoding="utf-8")
)["scenarios"]
normal = verify(req, ir, scenarios)
broken = ir.model_copy(deep=True)
broken.rungs[0].condition = broken.rungs[0].condition.items[0]  # 정지 접점 제거
fault = verify(req, broken, scenarios)
for name, report in [("normal_report.json", normal), ("broken_report.json", fault)]:
    Path(name).write_text(report.model_dump_json(indent=2), encoding="utf-8")
```

두 JSON을 편집기에서 열어 보세요. 정상은 `passed=true`, 고장은 `passed=false`예요.
고장 보고서의 C2 오류에는 Y0의 기대값 0, 실제값 1, 실패 시각 100ms가 있어요.
서버 저장이 아니라 로컬 파일 출력이며, 학생 확인란은 학생 본인만 체크해요.

```sh
cd backend
pytest -q tests/test_sim.py tests/test_scenarios.py tests/test_verify.py
pytest -q
```

**모의 실행 통과는 실제 설비 안전을 보장하지 않아요. 실제 설비 적용 전 전문가 확인 필요.**
보고서는 전달받은 시나리오만 검사하며, 자연어 조건의 의미를 충분히 검사하는지는
학생이 직접 확인해야 해요. GX Simulator·실제 PLC·CPU 매뉴얼 검증과 구분해요.

## 시험 틀(check)

조건마다 `check`(틀 이름 + 신호 이름)를 붙이면 코드가 시험 대본을 만들어요(`app/plc/checks.py`). 틀: self_hold, stop_priority, on_delay, timed_on, interlock, and_enable, or_enable, indicator, set_reset, custom(낮은 신뢰). 틀이 잘못되면 필수 조건은 INVALID_CHECK 오류, 분석 단계(finalize)에서는 틀을 버리고 가정에 남겨요. 판정은 `verify_with_checks`가 해요.

### 검증 연결 흐름

설계가 저장되면(`submit_design`) 서버가 곧바로 `run_verification`을 실행해요. 상태는 DESIGNING → VERIFYING → 통과 시 COMPLETED, 실패 시 ESCALATED(자동 수정 #43 전까지)로 가요. `verification` 이벤트에 조건별 PASS/FAIL/UNVERIFIED 표와 "모의 실행 기준" 안내가 담겨요. 계약 변경은 없어요.

