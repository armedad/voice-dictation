@echo off
REM Install script for voice-dictation (Windows)
REM Uses CHEEAPPS_VENV: folder for the virtualenv (same convention as gauth). If unset, the
REM path from .voice_dictation_venv is reused when present; otherwise you are prompted.
REM Non-interactive: set CHEEAPPS_VENV before running, e.g.
REM   set CHEEAPPS_VENV=C:\venvs\cheeapps-stack
REM   install.bat
REM Path is written to .voice_dictation_venv for start.bat.
REM
REM Capture parent env BEFORE setlocal — otherwise PowerShell/cmd may not pass
REM CHEEAPPS_VENV into this script reliably after setlocal runs.

set "CHEE_CAPTURE=%CHEEAPPS_VENV%"
setlocal EnableDelayedExpansion EnableExtensions
cd /d "%~dp0"
set "ROOT=%CD%"

rem --- defaults (mirror install.sh) ---
set "AGENT_ONLY=0"
set "SKIP_OLLAMA=0"
set "SKIP_WHISPER=0"
set "SKIP_TWIM=0"
set "WITH_SPIKE=0"
set "RECREATE_VENV=0"

:parse
if "%~1"=="" goto parsed
if /i "%~1"=="--agent-only" (set "AGENT_ONLY=1" & shift & goto parse)
if /i "%~1"=="--skip-ollama" (set "SKIP_OLLAMA=1" & shift & goto parse)
if /i "%~1"=="--skip-whisper" (set "SKIP_WHISPER=1" & shift & goto parse)
if /i "%~1"=="--skip-twim" (set "SKIP_TWIM=1" & shift & goto parse)
if /i "%~1"=="--skip-ai-frame" (set "SKIP_TWIM=1" & shift & goto parse)
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
echo   install.bat                  full: agent + twim + faster-whisper + ollama pull
echo   install.bat --agent-only     venv + requirements-agent.txt only
echo   install.bat --skip-ollama
echo   install.bat --skip-whisper
echo   install.bat --skip-twim
echo   install.bat --skip-ai-frame   ^(deprecated alias for --skip-twim^)
echo   install.bat --with-spike
echo   install.bat --recreate-venv
echo.
echo Env:
echo   CHEEAPPS_VENV                    virtualenv directory ^(required if no console and no .voice_dictation_venv^)
echo   VOICE_DICTATION_WHISPER_DEVICE   optional Whisper preload; default cpu
echo   VOICE_DICTATION_WHISPER_COMPUTE  default int8
exit /b 0

:parsed
if "%AGENT_ONLY%"=="1" (
  set "SKIP_TWIM=1"
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

echo ==^> Installing agent dependencies (requirements-agent.txt^) ...
echo     (PyObjC / quickmachotkey install only on macOS via PEP 508 markers; Windows uses pynput hotkeys.^)
python -m pip install -r requirements-agent.txt
if errorlevel 1 exit /b 1

if not "%SKIP_TWIM%"=="1" (
  echo ==^> Installing twim (settings UI^) dependencies ...
  python -m pip install -r twim\requirements.txt
  if errorlevel 1 exit /b 1
)

if "%WITH_SPIKE%"=="1" (
  echo ==^> Installing spike lab dependencies ...
  python -m pip install -r spike\requirements.txt
  if errorlevel 1 exit /b 1
)

if exist "%ROOT%\config\default-twim-settings.json" if not exist "%ROOT%\twim\users\_default\settings.json" (
  echo ==^> Seeding twim default settings ...
  if not exist "%ROOT%\twim\users\_default" mkdir "%ROOT%\twim\users\_default"
  copy /y "%ROOT%\config\default-twim-settings.json" "%ROOT%\twim\users\_default\settings.json" >nul
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
    echo ==^> Ollama models ^(agent example cleanup + TWIM default cleanup + eval judge^) ...
    set "OLLAMA_MODEL="
    for /f "usebackq delims=" %%m in (`python "%ROOT%\scripts\install_post_pip.py" print-ollama-cleanup-model`) do set "OLLAMA_MODEL=%%m"
    if defined OLLAMA_MODEL (
      echo ==^> Pulling !OLLAMA_MODEL! ^(agent example config cleanup^) ...
      ollama pull "!OLLAMA_MODEL!" || echo warning: ollama pull !OLLAMA_MODEL! failed.
    )
    set "PULL_ANY=0"
    for /f "usebackq tokens=1,2 delims=	" %%a in (`python "%ROOT%\scripts\install_post_pip.py" print-eval-ollama-models-to-pull`) do (
      set "PULL_ANY=1"
      echo ==^> Pulling %%b ^(%%a^) ...
      ollama pull "%%b" || echo warning: ollama pull %%b failed.
    )
    if "!PULL_ANY!"=="0" if not defined OLLAMA_MODEL (
      echo ==^> No Ollama models configured to pull.
    )
  )
)

echo.
echo ==^> Done.
echo     Venv path saved in .voice_dictation_venv. Next time: set CHEEAPPS_VENV=!VENV_DIR! to skip the prompt.
echo     Activate:  "!VENV_DIR!\Scripts\activate.bat"
echo     Pipeline CLI: python dictation_cli.py record-once --seconds 4 --no-type
echo     Settings:  start.bat from repo root ^(or run_combined_app.py / uvicorn per README^)
echo     Config:    %USERPROFILE%\.voice-dictation\config.json ^(created on first agent run if missing^)
echo     Note: global hotkey hooks ^(pynput^) may require AV exclusions if binds fail.
exit /b 0
