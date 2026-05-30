@echo off
title voice dictation
REM Resolve venv: CHEEAPPS_VENV, else .voice_dictation_venv, else .venv in this folder (same as gauth launch.bat).
set "CHEE_CAPTURE=%CHEEAPPS_VENV%"
setlocal EnableDelayedExpansion EnableExtensions
cd /d "%~dp0"
set "ROOT=%CD%"

rem Defaults (mirror start.sh combined mode on Windows)
if defined VOICE_DICTATION_PORT (set "PORT=%VOICE_DICTATION_PORT%") else (set "PORT=8946")
set "RELOAD=1"
set "SKIP_HOTKEY_AGENT=0"
set "BACKGROUND=0"

:parse
if "%~1"=="" goto parsed
if /i "%~1"=="--help" goto help
if /i "%~1"=="-h" goto help
if /i "%~1"=="-help" goto help
if /i "%~1"=="--background" (set "BACKGROUND=1" & shift & goto parse)
if /i "%~1"=="--port" (
  if "%~2"=="" (echo error: --port needs a value >&2 & exit /b 1)
  set "PORT=%~2"
  shift
  shift
  goto parse
)
if /i "%~1"=="--no-reload" (set "RELOAD=0" & shift & goto parse)
if /i "%~1"=="--skip-hotkey-agent" (set "SKIP_HOTKEY_AGENT=1" & shift & goto parse)
echo error: unknown option: %~1 ^(try start.bat --help^) >&2
exit /b 1

:help
echo Voice Dictation MVP — start settings UI + dictation API ^(Windows^).
echo.
echo Usage:
echo   start.bat                       ^(port from VOICE_DICTATION_PORT or 8946^)
echo   start.bat --port 8765
echo   start.bat --background          ^(no persistent console window^)
echo   start.bat --no-reload           ^(only applies with --skip-hotkey-agent^)
echo   start.bat --skip-hotkey-agent   ^(API only; allows --reload for dev^)
echo   start.bat --help, -h, -help
echo.
echo Venv: CHEEAPPS_VENV, or path in .voice_dictation_venv ^(written by install.bat^), else %%ROOT%%\.venv
echo.
echo Foreground ^(default^): combined app with global hotkeys ^(reload disabled^).
echo Background: always no reload. Logs: logs\hotkey-agent.log
exit /b 0

:parsed
if "!CHEE_CAPTURE!"=="" (
  if exist ".voice_dictation_venv" (
    for /f "usebackq delims=" %%i in (".voice_dictation_venv") do set "VENV_DIR=%%i"
  ) else (
    set "VENV_DIR=%ROOT%\.venv"
  )
) else (
  for %%I in ("!CHEE_CAPTURE!") do set "VENV_DIR=%%~fI"
)

set "VENV_PY=!VENV_DIR!\Scripts\python.exe"
if not exist "!VENV_PY!" (
  echo error: missing "!VENV_PY!" — run install.bat first ^(set CHEEAPPS_VENV for a shared venv path^). >&2
  exit /b 1
)

if "%BACKGROUND%"=="1" goto launch_background

echo.
echo   Voice Dictation MVP — combined app ^(uvicorn + global hotkeys when not skipped^)
echo   Open: http://127.0.0.1:%PORT%/
echo   Logs: %ROOT%\logs\hotkey-agent.log ^(when hotkeys enabled^)
echo   Global hooks may need antivirus exclusions if hotkeys do not fire.
echo.

if "%SKIP_HOTKEY_AGENT%"=="1" (
  if "%RELOAD%"=="1" (
    "!VENV_PY!" "%ROOT%\run_combined_app.py" --port "%PORT%" --skip-hotkey-agent --reload
  ) else (
    "!VENV_PY!" "%ROOT%\run_combined_app.py" --port "%PORT%" --skip-hotkey-agent
  )
) else (
  if "%RELOAD%"=="1" (
    echo warning: --reload is disabled when global hotkeys are enabled. >&2
  )
  "!VENV_PY!" "%ROOT%\run_combined_app.py" --port "%PORT%"
)
exit /b %ERRORLEVEL%

:launch_background
REM Stop an existing instance so the port is free (ignore errors if none is running).
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:%PORT%/api/local/shutdown' -Method POST -UseBasicParsing -TimeoutSec 3 | Out-Null } catch {}" >nul 2>&1
timeout /t 1 /nobreak >nul 2>&1

start "" /B cmd /c "cd /d "%~dp0" && set VOICE_DICTATION_BG_PORT=%PORT% && set VOICE_DICTATION_BG_SKIP_HOTKEY=%SKIP_HOTKEY_AGENT% && scripts\voice-dictation-background-worker.bat"
echo Voice dictation starting in background on http://127.0.0.1:%PORT%/
echo Logs: %ROOT%\logs\hotkey-agent.log
exit /b 0
