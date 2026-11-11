# frontend

PLC 필수 정보·동작 조건 입력, 에이전트 실행·진행 확인, 검증 결과, 웹 모의 실행 화면. Vite + React + TypeScript. 전체 구조는 [TRD](../docs/TRD.md)를 보세요.

## 실행
```
cd frontend
npm install
npm run dev      # 개발 서버 (/api/*는 백엔드 :8000으로 프록시)
npm run build    # 타입 검사 + 빌드
npm run lint
```

## 구성
- `src/spec.ts`, `src/validate.ts`: 시리즈·CPU·선택지와 필수·호환·점수·디바이스 검증(서버 `validation.py`와 같은 규칙)
- `src/App.tsx`, `SettingsStep.tsx`, `ConditionsStep.tsx`, `TemplatesCard.tsx`, `csv.ts`: 입력 화면, CSV 가져오기, 템플릿
- `src/RunStep.tsx`, `api.ts`: 에이전트 실행, 상태 폴링, 단계별·총 경과 시간
- `src/Result.tsx`, `Criteria.tsx`: 검증 결과, 신뢰도 배지, 검증 기준 팝업, 설계 보기
- `src/sim/`: 웹 모의 실행(엔진, 래더 보기, 시뮬레이터)
- `src/ui.tsx`: 공용 컴포넌트

## 남은 일
- IL 파일 내려받기와 GX Simulator 확인 안내 (#44)
- 한 화면 통합·배포 (#45)
- 실패한 작업의 사유를 마크다운으로 알기 쉽게 표시
