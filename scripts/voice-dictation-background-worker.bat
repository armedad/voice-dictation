@echo off
REM Background worker (no pause). Used by start.bat --background.
setlocal EnableDelayedExpansion EnableExtensions
cd /d "%~dp0\.."

if "%CHEEAPPS_VENV%"=="" (
  if exist ".voice_dictation_venv" (
    for /f "usebackq delims=" %%i in (".voice_dictation_venv") do set "VENV_DIR=%%i"
  ) else (
    set "VENV_DIR=%~dp0..\.venv"
  )
) else (
  for %%I in ("%CHEEAPPS_VENV%") do set "VENV_DIR=%%~fI"
)

set "VENV_PY=!VENV_DIR!\Scripts\python.exe"
if not exist "!VENV_PY!" exit /b 1

if not exist "logs" mkdir "logs"

if defined VOICE_DICTATION_BG_PORT (set "PORT=%VOICE_DICTATION_BG_PORT%") else (set "PORT=8946")
set "RUN_ARGS=--port %PORT%"
if "%VOICE_DICTATION_BG_SKIP_HOTKEY%"=="1" set "RUN_ARGS=!RUN_ARGS! --skip-hotkey-agent"

"!VENV_PY!" run_combined_app.py !RUN_ARGS!
