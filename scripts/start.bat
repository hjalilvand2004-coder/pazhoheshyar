@echo off
REM اجرای ساده با پایتون (سیستم‌هایی که پایتون دارند)
cd /d "%~dp0.."
if not exist frontend\dist (
  echo فرانت ساخته نشده؛ ابتدا در پوشه frontend اجرا کنید: npm install و npm run build
  pause
  exit /b 1
)
cd backend
python -m venv .venv 2>nul
call .venv\Scripts\activate
pip install -q -r requirements.txt
python run.py
pause
