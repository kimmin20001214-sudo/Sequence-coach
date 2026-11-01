@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Sequence Coach (이 창을 닫으면 서버도 꺼집니다)

set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=py"

if not exist backend\.venv (
  "%PY%" -m venv backend\.venv
  backend\.venv\Scripts\python.exe -m pip install -q -r backend\requirements.txt
)
if not exist frontend\node_modules (
  pushd frontend
  call npm.cmd install
  popd
)

rem 백엔드는 이 창의 백그라운드로, 프론트는 이 창에서 실행 -> 창을 닫으면 둘 다 종료
start /b "" cmd /c "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"
start "" /min cmd /c "timeout /t 6 >nul & start http://localhost:5173"

cd frontend
call npm.cmd run dev
