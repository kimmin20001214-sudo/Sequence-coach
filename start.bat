@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

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

start "Sequence Coach - backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"
start "Sequence Coach - frontend" cmd /k "cd /d %~dp0frontend && npm.cmd run dev"

timeout /t 6 >nul
start "" http://localhost:5173
