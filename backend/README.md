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
