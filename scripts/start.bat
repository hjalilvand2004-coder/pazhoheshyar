@echo off
REM Pazhoheshyar360 - simple launcher (requires Python 3.10+ on PATH)
REM NOTE: keep this file ASCII-only; Persian guide is in the TXT file next to it.
setlocal
REM Work whether this bat sits at the package root or inside scripts\
cd /d "%~dp0"
if not exist "frontend\dist\index.html" cd /d "%~dp0.."
if not exist "frontend\dist\index.html" (
  echo [ERROR] frontend\dist\index.html not found next to this launcher.
  echo Fix: re-download the full release zip - the frontend build is included.
  pause
  exit /b 1
)
where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found on PATH.
  echo Install Python 3.10+ from https://www.python.org/downloads/
  echo and enable "Add python.exe to PATH" during setup, then run this file again.
  pause
  exit /b 1
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo [ERROR] Python 3.10 or newer is required. Your version:
  python --version
  echo Please install Python 3.10+ from https://www.python.org/downloads/
  pause
  exit /b 1
)
cd backend
if not exist ".venv" (
  echo First run: creating virtual environment...
  python -m venv .venv
)
call ".venv\Scripts\activate.bat"
echo Checking dependencies ^(first run downloads numpy/scikit-learn, can take 5-10 minutes; later runs take a few seconds^)...
python -m pip install -r requirements.txt
echo.
echo Starting Pazhoheshyar360 ... the browser will open automatically.
echo If it does not open by itself, go to:  http://localhost:8088
echo KEEP THIS WINDOW OPEN while using the system - closing it stops the server.
echo.
python run.py
echo Server stopped.
pause
