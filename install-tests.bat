@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "INSTALL_ROOT=%CD%"
set "ROOT=%CD%"

rem --- defaults (mirror install-tests.sh) ---
set "SKIP_OLLAMA=0"
set "SKIP_WHISPER=0"
set "RECREATE_VENV=0"

:parse
if "%~1"=="" goto parsed
if /i "%~1"=="--skip-ollama" (set "SKIP_OLLAMA=1" & shift & goto parse)
if /i "%~1"=="--skip-whisper" (set "SKIP_WHISPER=1" & shift & goto parse)
if /i "%~1"=="--recreate-venv" (set "RECREATE_VENV=1" & shift & goto parse)
if /i "%~1"=="-h" goto help
if /i "%~1"=="--help" goto help
echo error: unknown option: %~1 ^(try install-tests.bat --help^)
exit /b 1

:help
echo Voice dictation MVP — install AI eval / test harness.
echo.
echo Does not start ollama serve ^(use Ollama app or existing server on port 11434^).
echo.
echo Usage:
echo   install-tests.bat
echo   install-tests.bat --skip-ollama
echo   install-tests.bat --skip-whisper
echo   install-tests.bat --recreate-venv
echo.
echo Env ^(optional, Whisper preload^):
echo   VOICE_DICTATION_WHISPER_DEVICE   default cpu
echo   VOICE_DICTATION_WHISPER_COMPUTE  default int8
echo   OLLAMA_HOST / OLLAMA_PORT        default 127.0.0.1 / 11434
exit /b 0

:parsed
echo ==^> Voice dictation test harness install (root: %ROOT%^)

python -c "import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)" 2>nul
if errorlevel 1 (
  echo error: need Python 3.10+ on PATH ^(https://www.python.org/downloads/^)
  exit /b 1
)

for /f "tokens=*" %%v in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set "PYVER=%%v"
echo ==^> Using python on PATH (Python %PYVER%^)

if "%RECREATE_VENV%"=="1" if exist .venv (
  echo ==^> Removing existing .venv ^(--recreate-venv^) ...
  rmdir /s /q .venv
)

if not exist .venv (
  echo ==^> Creating venv .venv ...
  py -3.13 -m venv .venv 2>nul
  if not exist .venv\Scripts\python.exe py -3.12 -m venv .venv 2>nul
  if not exist .venv\Scripts\python.exe py -3.11 -m venv .venv 2>nul
  if not exist .venv\Scripts\python.exe python -m venv .venv
  if not exist .venv\Scripts\python.exe (
    echo error: could not create .venv. Try: py -3.13 -m venv .venv
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

echo ==^> Installing test dependencies (requirements-dev.txt + requirements-eval.txt^) ...
python -m pip install -r requirements-dev.txt -r requirements-eval.txt
if errorlevel 1 exit /b 1

if not defined VOICE_DICTATION_WHISPER_DEVICE set "VOICE_DICTATION_WHISPER_DEVICE=cpu"
if not defined VOICE_DICTATION_WHISPER_COMPUTE set "VOICE_DICTATION_WHISPER_COMPUTE=int8"

if not "%SKIP_WHISPER%"=="1" (
  echo ==^> Pre-downloading faster-whisper weights (from evals\eval_config.json^) ...
  python "%ROOT%\scripts\install_post_pip.py" prefetch-whisper-eval
  if errorlevel 1 exit /b 1
)

if not defined OLLAMA_HOST set "OLLAMA_HOST=127.0.0.1"
if not defined OLLAMA_PORT set "OLLAMA_PORT=11434"
set "OLLAMA_BASE=http://%OLLAMA_HOST%:%OLLAMA_PORT%"

where curl >nul 2>&1
if errorlevel 1 (
  echo warning: curl not found; skipping Ollama reachability check.
) else (
  curl -fsS --max-time 2 "%OLLAMA_BASE%/api/tags" >nul 2>&1
  if errorlevel 1 (
    echo ==^> Ollama not reachable at %OLLAMA_BASE% ^(start Ollama app; avoid second ollama serve if port in use^).
  ) else (
    echo ==^> Ollama already reachable at %OLLAMA_BASE%
  )
)

if not "%SKIP_OLLAMA%"=="1" (
  where ollama >nul 2>&1
  if errorlevel 1 (
    echo warning: ollama not on PATH; skipped model pull. Install from https://ollama.com
  ) else (
    echo ==^> Pulling Ollama eval models (from evals\eval_config.json^) ...
    for /f "usebackq delims=" %%m in (`python "%ROOT%\scripts\install_post_pip.py" print-eval-ollama-models`) do (
      if not "%%m"=="" (
        ollama pull "%%m" || echo warning: ollama pull %%m failed.
      )
    )
  )
)

echo.
echo ==^> Done (test harness).
echo     Activate:  .venv\Scripts\activate.bat
echo     Unit tests:  pytest tests/ -q
echo     Evals (all): pytest evals/ -q
echo     STT only:    pytest evals/ -m slow -q
echo     Cleanup:     pytest evals/ -m requires_ollama -q
echo     GEval judge: set VOICE_DICTATION_RUN_GEVAL=1 ^& pytest evals/ -m geval_judge -q
echo     Config:      evals\eval_config.json
echo     macOS/Linux: ./install-tests.sh
exit /b 0
