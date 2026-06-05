@echo off
REM Patent Filing QC - double-click launcher (Windows).
REM First run creates a private Python environment (.venv) and installs
REM dependencies (needs internet that one time). Later runs start instantly
REM and work offline. Closing this window stops the tool.

cd /d "%~dp0"

REM Find Python: prefer the 'py' launcher, fall back to 'python' on PATH.
set "PYLAUNCH="
where py >nul 2>nul && set "PYLAUNCH=py -3"
if not defined PYLAUNCH (
  where python >nul 2>nul && set "PYLAUNCH=python"
)
if not defined PYLAUNCH (
  echo Python 3 is not installed.
  echo Install it from https://www.python.org/downloads/ ^(check "Add Python to PATH"^) and try again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo First-time setup - creating a local environment and installing dependencies...
  %PYLAUNCH% -m venv .venv || (echo Could not create the environment. & pause & exit /b 1)
  ".venv\Scripts\python" -m pip install --quiet --upgrade pip
  ".venv\Scripts\python" -m pip install --quiet -r requirements.txt || (
    echo Dependency install failed. Check your internet connection and try again. & pause & exit /b 1)
  echo Setup complete.
)

echo Starting Patent Filing QC... your browser will open shortly.
".venv\Scripts\python" app\server.py
