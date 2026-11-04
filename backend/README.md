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
