@echo off
REM Run unit/API pytest (tests\) and AI evals (evals\: jiwer STT + DeepEval cleanup).
REM Prereq: install-tests.bat. Ollama required for cleanup evals; STT evals are slow (Whisper).
REM Venv: CHEEAPPS_VENV, else .voice_dictation_venv, else .venv

set "CHEE_CAPTURE=%CHEEAPPS_VENV%"
setlocal EnableDelayedExpansion EnableExtensions
cd /d "%~dp0"
set "ROOT=%CD%"

set "UNIT_ONLY=0"
set "EVAL_ONLY=0"
set "SKIP_SLOW=0"
set "SKIP_GEVAL=0"
set "NO_LOG=0"
set "PYTEST_EXTRA="

:parse
if "%~1"=="" goto parsed
if /i "%~1"=="--unit-only" (set "UNIT_ONLY=1" & shift & goto parse)
if /i "%~1"=="--evals-only" (set "EVAL_ONLY=1" & shift & goto parse)
if /i "%~1"=="--skip-slow" (set "SKIP_SLOW=1" & shift & goto parse)
if /i "%~1"=="--skip-geval" (set "SKIP_GEVAL=1" & shift & goto parse)
if /i "%~1"=="--no-log" (set "NO_LOG=1" & shift & goto parse)
if /i "%~1"=="--with-geval" (
  echo warning: --with-geval is deprecated ^(GEval runs by default^). Use --skip-geval to omit.
  shift
  goto parse
)
if /i "%~1"=="-q" (set "PYTEST_EXTRA=-q" & shift & goto parse)
if /i "%~1"=="--quiet" (set "PYTEST_EXTRA=-q" & shift & goto parse)
if /i "%~1"=="-v" (set "PYTEST_EXTRA=-v" & shift & goto parse)
if /i "%~1"=="--verbose" (set "PYTEST_EXTRA=-v" & shift & goto parse)
if /i "%~1"=="-h" goto help
if /i "%~1"=="--help" goto help
echo error: unknown option: %~1 ^(try run-tests.bat --help^)
exit /b 1

:help
echo run-tests.bat — run the voice-dictation MVP test suite
echo.
echo USAGE
echo   run-tests.bat [OPTIONS]
echo.
echo   With no options: runs tests\ + evals\ ^(unit, API, STT WER, cleanup gates, GEval judge^).
echo.
echo DEFAULTS
echo   DeepEval GEval judge tests run automatically.
echo   Use --skip-geval to omit them ^(faster; deterministic cleanup gates still run^).
echo.
echo OPTIONS
echo   -h, --help
echo       Show this help and exit.
echo.
echo   --unit-only
echo       Run only tests\ ^(fast deterministic pytest^). No evals\.
echo.
echo   --evals-only
echo       Run only evals\ ^(STT WER + cleanup regression^).
echo.
echo   --skip-slow
echo       Exclude faster-whisper WER cases ^(pytest -m "not slow"^).
echo.
echo   --skip-geval
echo       Skip DeepEval GEval judge tests ^(sets VOICE_DICTATION_SKIP_GEVAL=1^).
echo.
echo   -q, --quiet     Quiet pytest output.
echo   -v, --verbose   Verbose pytest output.
echo.
echo   --no-log
echo       Do not write logs\test-runs\pytest-^<timestamp^>.log or .xml.
echo.
echo LOGGING ^(default^)
echo   Each run creates new files under logs\test-runs\ ^(not appended^):
echo     pytest-YYYYMMDD-HHMMSS.log  — full output
echo     pytest-YYYYMMDD-HHMMSS.xml  — JUnit XML
echo.
echo ENVIRONMENT
echo   CHEEAPPS_VENV              Virtualenv directory ^(.voice_dictation_venv or .venv fallback^)
echo   VOICE_DICTATION_SKIP_GEVAL Set by --skip-geval
echo   OLLAMA_HOST / OLLAMA_PORT  Ollama for cleanup evals; errors if down when evals\ run
echo.
echo EXAMPLES
echo   run-tests.bat
echo   run-tests.bat --unit-only -q
echo   run-tests.bat --evals-only --skip-geval
echo   run-tests.bat --skip-slow
echo.
echo PREREQUISITES
echo   install-tests.bat once. Ollama must be running for evals\ ^(errors if not^).
exit /b 0

:parsed
if "%UNIT_ONLY%"=="1" if "%EVAL_ONLY%"=="1" (
  echo error: --unit-only and --evals-only are mutually exclusive
  exit /b 1
)

if not "!CHEE_CAPTURE!"=="" (
  for %%I in ("!CHEE_CAPTURE!") do set "VENV_DIR=%%~fI"
) else if exist ".voice_dictation_venv" (
  for /f "usebackq delims=" %%i in (".voice_dictation_venv") do set "VENV_DIR=%%i"
) else (
  set "VENV_DIR=%ROOT%\.venv"
)

set "PY=!VENV_DIR!\Scripts\python.exe"
if not exist "!PY!" (
  echo error: no venv at !VENV_DIR! ^(run install-tests.bat first^)
  exit /b 1
)

"!PY!" -c "import pytest" 2>nul
if errorlevel 1 (
  echo error: pytest not installed in venv. Run: install-tests.bat
  exit /b 1
)

set "PATHS=tests/ evals/"
if "%EVAL_ONLY%"=="1" set "PATHS=evals/"
if "%UNIT_ONLY%"=="1" set "PATHS=tests/"

set "MARKER_ARGS="
if "%SKIP_SLOW%"=="1" set "MARKER_ARGS=-m \"not slow\""

if "%SKIP_GEVAL%"=="1" (
  set "VOICE_DICTATION_SKIP_GEVAL=1"
  set "VOICE_DICTATION_RUN_GEVAL=0"
) else (
  set "VOICE_DICTATION_SKIP_GEVAL="
  set "VOICE_DICTATION_RUN_GEVAL=1"
)

echo ==^> Voice dictation tests ^(venv: !VENV_DIR!^)
echo     Paths: !PATHS!
if "%SKIP_SLOW%"=="1" echo     Markers: not slow
if "%SKIP_GEVAL%"=="1" (
  echo     GEval judge: skipped ^(--skip-geval^)
) else (
  echo     GEval judge: enabled ^(default^)
)

echo !PATHS! | findstr /i /c:"evals" >nul
if not errorlevel 1 (
  echo     Checking Ollama ^(required for evals\^)...
  "!PY!" -c "from evals.helpers import require_ollama_for_evals; require_ollama_for_evals()"
  if errorlevel 1 exit /b 1
)

if "%NO_LOG%"=="1" (
  "!PY!" -m pytest !PATHS! !PYTEST_EXTRA! !MARKER_ARGS!
  exit /b !ERRORLEVEL!
)

set "LOG_DIR=%ROOT%\logs\test-runs"
if not exist "!LOG_DIR!" mkdir "!LOG_DIR!"

for /f "delims=" %%t in ('powershell -NoProfile -Command "Get-Date -Format ''yyyyMMdd-HHmmss''"') do set "STAMP=%%t"
set "LOG_FILE=!LOG_DIR!\pytest-!STAMP!.log"
set "JUNIT_FILE=!LOG_DIR!\pytest-!STAMP!.xml"
echo     Log:   !LOG_FILE!
echo     JUnit: !JUNIT_FILE!

"!PY!" -m pytest !PATHS! !PYTEST_EXTRA! !MARKER_ARGS! --junitxml="!JUNIT_FILE!" > "!LOG_FILE!" 2>&1
set "EXIT_CODE=!ERRORLEVEL!"
type "!LOG_FILE!"
exit /b !EXIT_CODE!
