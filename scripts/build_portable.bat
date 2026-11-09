@echo off
REM ساخت نسخه اجرایی مستقل ویندوز (بدون نیاز به پایتون روی سیستم مقصد)
REM پیش‌نیاز روی سیستم ساخت: پایتون ۳.۱۰+ و Node.js ۱۸+
cd /d "%~dp0.."
echo ==^> 1/4 ساخت فرانت React
cd frontend
call npm ci --no-audit --no-fund || call npm install --no-audit --no-fund
call npm run build
cd ..\backend
echo ==^> 2/4 نصب وابستگی‌ها و PyInstaller
python -m pip install -r requirements-build.txt
echo ==^> 3/4 بسته‌بندی
python -m PyInstaller PazhoheshYar.spec --noconfirm
echo ==^> 4/4 اتمام
echo فایل اجرایی: backend\dist\pazhoheshyar360-server.exe
echo اجرا: دوبار کلیک روی فایل، سپس مرورگر: http://localhost:8000
pause
