@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [RiskVolume] Creating virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo [RiskVolume] Failed to create .venv. Install Python 3.10+ and try again.
    pause
    exit /b 1
  )
)

echo [RiskVolume] Installing/updating dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [RiskVolume] Dependency installation failed.
  pause
  exit /b 1
)

echo [RiskVolume] Starting application...
".venv\Scripts\python.exe" main.py
endlocal
