@echo off
REM Install AI eval / test harness (pytest, deepeval, jiwer, models).
REM Uses CHEEAPPS_VENV: folder for the virtualenv (same convention as install.bat). If unset, the
REM path from .voice_dictation_venv is reused when present; otherwise you are prompted.
REM Non-interactive: set CHEEAPPS_VENV before running, e.g.
REM   set CHEEAPPS_VENV=C:\venvs\cheeapps-stack
REM   install-tests.bat
REM Path is written to .voice_dictation_venv for start.bat.
REM Does not start ollama serve.

set "CHEE_CAPTURE=%CHEEAPPS_VENV%"
setlocal EnableDelayedExpansion EnableExtensions
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
echo Env:
echo   CHEEAPPS_VENV                    virtualenv directory ^(required if no console and no .voice_dictation_venv^)
echo   VOICE_DICTATION_WHISPER_DEVICE   optional Whisper preload; default cpu
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

if "!CHEE_CAPTURE!"=="" (
  if exist ".voice_dictation_venv" (
    for /f "usebackq delims=" %%i in (".voice_dictation_venv") do set "CHEE_CAPTURE=%%i"
  )
)
if "!CHEE_CAPTURE!"=="" (
  python -c "import sys; raise SystemExit(0 if sys.stdin.isatty() else 1)" 2>nul
  if errorlevel 1 (
    echo Error: CHEEAPPS_VENV must be set when running non-interactively ^(no console input^).
    echo Example: set CHEEAPPS_VENV=C:\venvs\cheeapps-stack
    echo Or run from an interactive Command Prompt to enter the venv path when prompted.
    pause
    exit /b 1
  )
  set /p "CHEE_CAPTURE=Path for virtual environment (created if missing): "
)
set "GV=!CHEE_CAPTURE!"
if "!GV!"=="" (
  echo Error: path is required ^(set CHEEAPPS_VENV, reuse .voice_dictation_venv, or enter a path when prompted^).
  pause
  exit /b 1
)
for %%I in ("!GV!") do set "VENV_DIR=%%~fI"

echo Virtual environment: !VENV_DIR!
(echo !VENV_DIR!)> .voice_dictation_venv

if "%RECREATE_VENV%"=="1" (
  if exist "!VENV_DIR!\pyvenv.cfg" (
    echo ==^> Removing existing venv ^(--recreate-venv^) at !VENV_DIR! ...
    rmdir /s /q "!VENV_DIR!"
  ) else if exist "!VENV_DIR!" (
    echo error: --recreate-venv: directory exists but is not a Python venv ^(missing pyvenv.cfg^).
    exit /b 1
  )
)

if exist "!VENV_DIR!\pyvenv.cfg" (
  echo ==^> Using existing virtual environment.
) else if exist "!VENV_DIR!" (
  echo error: directory exists but is not a Python venv ^(missing pyvenv.cfg^).
  exit /b 1
) else (
  echo ==^> Creating virtual environment...
  py -3.13 -m venv "!VENV_DIR!" 2>nul
  if not exist "!VENV_DIR!\Scripts\python.exe" py -3.12 -m venv "!VENV_DIR!" 2>nul
  if not exist "!VENV_DIR!\Scripts\python.exe" py -3.11 -m venv "!VENV_DIR!" 2>nul
  if not exist "!VENV_DIR!\Scripts\python.exe" python -m venv "!VENV_DIR!"
  if not exist "!VENV_DIR!\Scripts\python.exe" (
    echo error: could not create venv at !VENV_DIR!. Try: py -3.13 -m venv "!VENV_DIR!"
    exit /b 1
  )
)

call "!VENV_DIR!\Scripts\activate.bat"
if errorlevel 1 (
  echo error: failed to activate "!VENV_DIR!\Scripts\activate.bat"
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
    echo ==^> Ollama eval models ^(evals\eval_config.json: cleanup llama3.2:3b, judge qwen2.5:3b-instruct^) ...
    set "PULL_ANY=0"
    for /f "usebackq tokens=1,2 delims=	" %%a in (`python "%ROOT%\scripts\install_post_pip.py" print-eval-ollama-models-to-pull`) do (
      set "PULL_ANY=1"
      echo ==^> Pulling %%b ^(%%a^) ...
      ollama pull "%%b" || echo warning: ollama pull %%b failed.
    )
    if "!PULL_ANY!"=="0" (
      echo ==^> Eval models already present ^(or Ollama unreachable — start Ollama and re-run to pull^).
    )
  )
)

echo.
echo ==^> Done (test harness).
echo     Venv path saved in .voice_dictation_venv. Next time: set CHEEAPPS_VENV=!VENV_DIR! to skip the prompt.
echo     Activate:  "!VENV_DIR!\Scripts\activate.bat"
echo     Full suite:  run-tests.bat
echo     Unit tests:  pytest tests/ -q
echo     Evals (all): pytest evals/ -q
echo     STT only:    pytest evals/ -m slow -q
echo     Cleanup:     pytest evals/ -m requires_ollama -q
echo     Skip GEval:  run-tests.bat --skip-geval
echo     Config:      evals\eval_config.json
echo     macOS/Linux: ./install-tests.sh
exit /b 0
