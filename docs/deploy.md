# 배포 문서

> **로그인이 필요해요.** 계정은 팀장이 만들고, 로그인한 사람만 화면과 AI 분석을 쓸 수 있어요. 에이전트 도구(`/agent/*`, `/mcp`)는 로그인 대신 `AGENT_API_KEY`로 막아요. 계정 만드는 법은 아래 "계정 관리"를 보세요. (이슈 #45)

## 구조

- 한 개의 Docker 이미지에 프론트엔드(React 빌드)와 백엔드(FastAPI)가 같이 들어 있어요. (`Dockerfile`)
- 백엔드가 `/api`와 화면 파일을 함께 서비스해요. 포트는 `PORT` 환경변수를 써요(기본 8000).
- 데이터는 SQLite 파일 하나예요. 모의 실행은 브라우저에서 돌아서 별도 워커가 필요 없어요.
- Render 설정은 `render.yaml`에 있어요(무료 플랜, 헬스체크 `/api/health`).

## 환경변수 (비밀값은 저장소에 올리지 않아요)

| 이름 | 용도 | 비고 |
|---|---|---|
| `COPILOT_DIRECTLINE_SECRET` | Copilot Studio 에이전트 연결 | **비밀**. 또는 `COPILOT_TOKEN_ENDPOINT` |
| `COPILOT_DIRECTLINE_URL` | Direct Line 주소 | 선택, 기본값 있음 |
| `COPILOT_TIMEOUT_SECONDS` | 에이전트 응답 대기 시간 | 선택, 기본 180 |
| `AGENT_API_KEY` | 에이전트가 서버 도구를 부를 때 쓰는 키 | **비밀** |
| `DATABASE_PATH` | SQLite 파일 위치 | 선택, 기본 `data.sqlite3` |
| `FIX_ENABLED` | `1`이면 수정 에이전트 사용 | 선택 |
| `ACCOUNTS` | 시작할 때 없는 계정을 만들어요. 예: `leader:비밀번호8자이상:admin,s01:비밀번호8자이상` | **비밀**. 무료 플랜은 재시작하면 DB가 비어서 이 값으로 다시 만들어요 |
| `AUTH_DISABLED` | `1`이면 로그인을 끔 | **배포에서는 쓰지 않아요** (테스트·로컬 전용) |
| `AGENT_DEMO` | `1`이면 AI 없이 데모 모드 | **배포에서는 쓰지 않아요** |

## 로컬에서 실행

- AI 없이 화면 확인: `start-demo.bat`
- 에이전트 연결 실행: 위 환경변수를 설정한 뒤 `start.bat`

## Render 배포 순서

1. **배포 전 점검표**(아래)를 모두 끝내요.
2. Render에서 이 저장소로 Web Service(Docker)를 만들면 `render.yaml`이 적용돼요.
3. Render의 **Environment**에 위 비밀값을 직접 입력해요.
4. 배포가 끝나면 `https://<서비스 주소>/api/health`가 정상 응답하는지 확인해요.
5. 화면에서 예시 하나를 끝까지 실행해 봐요(설정 → 조건 → 설계 → 검증 → 모의 실행 → 파일 받기).

## 계정 관리

- **내 컴퓨터:** `backend` 폴더에서 `python -m app.manage add student01`(비밀번호는 실행 중에 물어봐요). `--admin`은 팀장 계정, `password`·`disable`·`enable`·`list`도 있어요.
- **Render(셸 없음):** `ACCOUNTS` 환경변수로 만들어요. 계정을 추가하려면 값을 고치고 다시 배포해요. 이미 있는 아이디는 비밀번호를 바꾸지 않아요.
- 로그인은 12시간 유지돼요. 5번 틀리면 1분간 잠겨요. 프로젝트와 템플릿은 만든 사람에게만 보여요(기본 템플릿은 모두).
- 서버는 `x-forwarded-proto`가 `https`일 때 쿠키에 Secure를 붙여요. Render는 이 값을 보내 줘요.

## 알아둘 점

- **무료 플랜 제한:** 일정 시간 요청이 없으면 서버가 잠들어 첫 접속이 느려요. 디스크가 없어서 **재시작하면 SQLite 데이터가 사라져요.** 데이터를 남기려면 유료 디스크가 필요해요.
- **AI 에이전트 지침은 자동으로 반영되지 않아요.** `docs/copilot-studio.md`가 바뀌면 Copilot Studio에 직접 붙여 넣어야 해요.
- **CI:** PR마다 백엔드 `pytest`, 프론트 `lint`·`build`가 돌아요. 통과해야 합쳐요.

## 배포 전 점검표

- [ ] 노출된 Direct Line 비밀키와 API 키를 **새로 발급해서 교체**했어요 (채팅 등에 노출된 적 있는 값은 폐기).
- [ ] 비밀값이 저장소·이슈·화면 캡처에 없어요.
- [ ] `ACCOUNTS`로 팀장·학생 계정을 정했고, 로그인이 되는지 확인했어요.
- [ ] 비용 한도(Copilot Studio 사용량)를 정했어요.
- [ ] `AGENT_DEMO`가 켜져 있지 않아요.
- [ ] Copilot Studio의 에이전트 4개 지침이 `docs/copilot-studio.md`와 같아요.
- [ ] 예시 하나를 끝까지 직접 실행해 확인했어요.
