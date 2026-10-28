# frontend

PLC 필수 정보·동작 조건 입력 화면 (#39). Vite + React + TypeScript.

## 실행
```
cd frontend
npm install
npm run dev      # 개발 서버
npm run build    # 타입 검사 + 빌드
npm run lint
```

## 구성
- `src/spec.ts`: 시리즈·CPU·선택지와 타입 (임시 내장, #38의 `/meta` API로 교체 예정)
- `src/validate.ts`: 필수·호환·점수·디바이스(16진/8진) 검증
- `src/SettingsStep.tsx`, `src/ConditionsStep.tsx`, `src/App.tsx`: 화면
- `src/ui.tsx`: 공용 컴포넌트(Card, Field, Chips, Segmented)

## 남은 일
- 백엔드 `POST /projects`, `POST /projects/{id}/requirements` 연동 (현재는 localStorage 임시 저장)
- 백엔드에서도 같은 검증을 최종 수행
