@echo off
REM Pazhoheshyar360 - simple launcher (requires Python 3.10+ on PATH)
REM NOTE: keep this file ASCII-only; Persian guide is in the TXT file next to it.
setlocal
REM Work whether this bat sits at the package root or inside scripts\
cd /d "%~dp0"
if not exist "frontend\dist\index.html" cd /d "%~dp0.."
if not exist "frontend\dist\index.html" (
  echo [ERROR] frontend\dist\index.html not found next to this launcher.
  echo Fix: open a terminal in the "frontend" folder and run:  npm install  then  npm run build
  echo OR re-download the full release zip - the frontend build is included.
  pause
  exit /b 1
)
cd backend
if not exist ".venv" (
  echo First run: creating virtual environment and installing dependencies ^(numpy/scikit-learn included, takes a few minutes^)...
  python -m venv .venv
)
call ".venv\Scripts\activate.bat"
python -m pip install -q -r requirements.txt
echo Starting Pazhoheshyar360 on http://localhost:8088 ...
python run.py
pause
