@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%CD%"

rem Defaults (mirror start.sh combined mode on Windows)
if defined VOICE_DICTATION_PORT (set "PORT=%VOICE_DICTATION_PORT%") else (set "PORT=8000")
set "RELOAD=1"
set "SKIP_HOTKEY_AGENT=0"

:parse
if "%~1"=="" goto parsed
if /i "%~1"=="--port" (
  if "%~2"=="" (echo error: --port needs a value >&2 & exit /b 1)
  set "PORT=%~2"
  shift
  shift
  goto parse
)
if /i "%~1"=="--no-reload" (set "RELOAD=0" & shift & goto parse)
if /i "%~1"=="--skip-hotkey-agent" (set "SKIP_HOTKEY_AGENT=1" & shift & goto parse)
if /i "%~1"=="-h" goto help
if /i "%~1"=="--help" goto help
echo error: unknown option: %~1 ^(try start.bat --help^) >&2
exit /b 1

:help
echo Voice Dictation MVP — start settings UI + dictation API ^(Windows^).
echo.
echo Usage:
echo   start.bat                       ^(port from VOICE_DICTATION_PORT or 8000^)
echo   start.bat --port 8765
echo   start.bat --no-reload           ^(only applies with --skip-hotkey-agent^)
echo   start.bat --skip-hotkey-agent   ^(API only; allows --reload for dev^)
echo.
exit /b 0

:parsed
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo error: missing "%VENV_PY%" — run install.bat first. >&2
  exit /b 1
)

echo.
echo   Voice Dictation MVP — combined app ^(uvicorn + global hotkeys when not skipped^)
echo   Open: http://127.0.0.1:%PORT%/
echo   Logs: %ROOT%\logs\hotkey-agent.log ^(when hotkeys enabled^)
echo   Global hooks may need antivirus exclusions if hotkeys do not fire.
echo.

if "%SKIP_HOTKEY_AGENT%"=="1" (
  if "%RELOAD%"=="1" (
    "%VENV_PY%" "%ROOT%\run_combined_app.py" --port "%PORT%" --skip-hotkey-agent --reload
  ) else (
    "%VENV_PY%" "%ROOT%\run_combined_app.py" --port "%PORT%" --skip-hotkey-agent
  )
) else (
  if "%RELOAD%"=="1" (
    echo warning: --reload is disabled when global hotkeys are enabled. >&2
  )
  "%VENV_PY%" "%ROOT%\run_combined_app.py" --port "%PORT%"
)
exit /b %ERRORLEVEL%
