# frontend

입력 화면(#39). 빌드 도구 없이 동작하는 순수 HTML/JS(ES 모듈)예요.

## 실행
`frontend` 폴더를 정적 서버로 열어요. (ES 모듈이라 `file://`로는 열리지 않아요.)
```
cd frontend
npx serve .        # Node.js가 있을 때
```
브라우저에서 표시된 주소를 열어요.

## 구성
- `src/spec.js`: 시리즈·CPU·선택지 (임시 내장, #38의 `/meta` API로 교체 예정)
- `src/validate.js`: 필수·호환·점수·디바이스(16진/8진) 검증
- `src/app.js`: 화면 (설정 → 동작 조건 → 완료)

## 남은 일
- 백엔드 `POST /projects`, `POST /projects/{id}/requirements` 연동 (현재는 브라우저 localStorage에 임시 저장)
- 백엔드에서도 같은 검증을 최종 수행
