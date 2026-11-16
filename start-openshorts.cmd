@echo off
setlocal
cd /d "%~dp0"
title OpenShorts launcher

where ollama >nul 2>nul || (echo Ollama is not installed or not on PATH. & pause & exit /b 1)
where bun >nul 2>nul || (echo Bun is not installed or not on PATH. & pause & exit /b 1)
where uv >nul 2>nul || (echo uv is not installed or not on PATH. & pause & exit /b 1)
set "PYTHONPATH=%~dp0win_shims"
set UV_ARGS=--no-project --python 3.12 --with-requirements requirements-local-windows.lock --index https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match
if not exist "dashboard\node_modules" (echo Installing dashboard packages... & pushd dashboard & call bun install & popd)

curl -s -o nul --max-time 3 http://localhost:11434/api/tags
if errorlevel 1 (
  echo Starting Ollama...
  start "OpenShorts - Ollama" /min cmd /c "ollama serve"
) else (
  echo Ollama already running.
)

curl -s -o nul --max-time 3 http://127.0.0.1:8000/api/config
if errorlevel 1 (
  echo Starting API...
  start "OpenShorts - API" cmd /k "uv run %UV_ARGS% python -m uvicorn app:app --host 127.0.0.1 --port 8000"
) else (
  echo API already running.
)

curl -s -o nul --max-time 3 http://localhost:5173/
if errorlevel 1 (
  echo Starting dashboard...
  start "OpenShorts - Dashboard" cmd /k "cd /d dashboard && set "VITE_PROXY_TARGET=http://127.0.0.1:8000" && bun run dev"
) else (
  echo Dashboard already running.
)

echo Waiting for the API...
set /a tries=0
:wait_api
curl -s -o nul --max-time 3 http://127.0.0.1:8000/api/config
if not errorlevel 1 goto ready
set /a tries+=1
if %tries% geq 300 (echo The API did not start: check the "OpenShorts - API" window. & pause & exit /b 1)
ping -n 3 127.0.0.1 >nul
goto wait_api

:ready
echo Ready: opening http://localhost:5173/#app
start "" "http://localhost:5173/#app"
endlocal
