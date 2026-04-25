@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "INSTALL_ROOT=%CD%"
set "ROOT=%CD%"

rem --- defaults (mirror install.sh) ---
set "AGENT_ONLY=0"
set "SKIP_OLLAMA=0"
set "SKIP_WHISPER=0"
set "SKIP_AI_FRAME=0"
set "WITH_SPIKE=0"
set "RECREATE_VENV=0"

:parse
if "%~1"=="" goto parsed
if /i "%~1"=="--agent-only" (set "AGENT_ONLY=1" & shift & goto parse)
if /i "%~1"=="--skip-ollama" (set "SKIP_OLLAMA=1" & shift & goto parse)
if /i "%~1"=="--skip-whisper" (set "SKIP_WHISPER=1" & shift & goto parse)
if /i "%~1"=="--skip-ai-frame" (set "SKIP_AI_FRAME=1" & shift & goto parse)
if /i "%~1"=="--with-spike" (set "WITH_SPIKE=1" & shift & goto parse)
if /i "%~1"=="--recreate-venv" (set "RECREATE_VENV=1" & shift & goto parse)
if /i "%~1"=="-h" goto help
if /i "%~1"=="--help" goto help
echo error: unknown option: %~1 ^(try install.bat --help^)
exit /b 1

:help
echo Voice dictation MVP — Windows install (venv, pip deps, optional Whisper/Ollama).
echo.
echo Usage:
echo   install.bat                  full: agent + ai-frame + faster-whisper + ollama pull
echo   install.bat --agent-only     venv + requirements-agent.txt only
echo   install.bat --skip-ollama
echo   install.bat --skip-whisper
echo   install.bat --skip-ai-frame
echo   install.bat --with-spike
echo   install.bat --recreate-venv
echo.
echo Env (optional, Whisper preload^):
echo   VOICE_DICTATION_WHISPER_DEVICE   default cpu
echo   VOICE_DICTATION_WHISPER_COMPUTE  default int8
exit /b 0

:parsed
if "%AGENT_ONLY%"=="1" (
  set "SKIP_AI_FRAME=1"
  set "SKIP_OLLAMA=1"
  set "SKIP_WHISPER=1"
  set "WITH_SPIKE=0"
)

echo ==^> Voice dictation MVP install (root: %ROOT%^)

python -c "import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)" 2>nul
if errorlevel 1 (
  echo error: need Python 3.10+ on PATH ^(install from https://www.python.org/downloads/^)
  exit /b 1
)

for /f "tokens=*" %%v in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set "PYVER=%%v"
echo ==^> Using python on PATH (Python %PYVER%^)
python -c "import sys; exit(0 if sys.version_info>=(3,10) else 1)" 2>nul
if errorlevel 1 echo warning: Python ^< 3.10 may hit typing issues; 3.11+ recommended.

if "%RECREATE_VENV%"=="1" if exist .venv (
  echo ==^> Removing existing .venv ^(--recreate-venv^) ...
  rmdir /s /q .venv
)

if not exist .venv (
  echo ==^> Creating venv .venv ...
  py -3.12 -m venv .venv 2>nul
  if not exist .venv\Scripts\python.exe py -3.11 -m venv .venv 2>nul
  if not exist .venv\Scripts\python.exe python -m venv .venv
  if not exist .venv\Scripts\python.exe (
    echo error: could not create .venv. Try: py -3.12 -m venv .venv
    exit /b 1
  )
) else (
  echo ==^> Reusing existing .venv ^(use --recreate-venv to start clean^) ...
)

call .venv\Scripts\activate.bat
if errorlevel 1 (
  echo error: failed to activate .venv\Scripts\activate.bat
  exit /b 1
)

python -m pip install -U pip wheel setuptools

echo ==^> Installing agent dependencies (requirements-agent.txt^) ...
echo     (includes PyObjC for macOS Carbon hotkeys when you use this tree on Mac; Windows skips unused wheels^)
python -m pip install -r requirements-agent.txt
if errorlevel 1 exit /b 1

if not "%SKIP_AI_FRAME%"=="1" (
  echo ==^> Installing ai-frame (settings UI^) dependencies ...
  python -m pip install -r ai-frame\requirements.txt
  if errorlevel 1 exit /b 1
)

if "%WITH_SPIKE%"=="1" (
  echo ==^> Installing spike lab dependencies ...
  python -m pip install -r spike\requirements.txt
  if errorlevel 1 exit /b 1
)

if not defined VOICE_DICTATION_WHISPER_DEVICE set "VOICE_DICTATION_WHISPER_DEVICE=cpu"
if not defined VOICE_DICTATION_WHISPER_COMPUTE set "VOICE_DICTATION_WHISPER_COMPUTE=int8"

if not "%SKIP_WHISPER%"=="1" (
  echo ==^> Pre-downloading faster-whisper weights (from config\example-model-settings.json^) ...
  python "%ROOT%\scripts\install_post_pip.py" prefetch-whisper
  if errorlevel 1 exit /b 1
)

if not "%SKIP_OLLAMA%"=="1" (
  where ollama >nul 2>&1
  if errorlevel 1 (
    echo warning: ollama not on PATH; skipped model pull. Install from https://ollama.com
  ) else (
    echo ==^> Pulling Ollama cleanup model (from config\example-model-settings.json^) ...
    set "OLLAMA_MODEL="
    for /f "usebackq delims=" %%m in (`python "%ROOT%\scripts\install_post_pip.py" print-ollama-cleanup-model`) do set "OLLAMA_MODEL=%%m"
    if defined OLLAMA_MODEL (
      ollama pull "%OLLAMA_MODEL%" || echo warning: ollama pull failed.
    ) else (
      echo ==^> Skipping ollama pull ^(cleanup.provider is not ollama_chat in example config.^)
    )
  )
)

echo.
echo ==^> Done.
echo     Activate:  .venv\Scripts\activate.bat
echo     Agent:     python run_agent.py record-once --seconds 4 --no-type
echo     Settings:  start from repo root per README ^(uvicorn / start.sh on Mac^)
echo     Config:    %USERPROFILE%\.voice-dictation\config.json ^(created on first agent run if missing^)
exit /b 0
