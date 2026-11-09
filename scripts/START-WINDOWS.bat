@echo off
REM اجرای بسته مستقل پژوهشیار۳۶۰ روی ویندوز — به پایتون نیازی نیست
chcp 65001 >nul
title Pazhoheshyar360 Server
cd /d "%~dp0"

echo ============================================
echo   پژوهشیار۳۶۰ - نسخه اجرایی مستقل
echo ============================================
echo سرور در حال روشن شدن است...

REM باز کردن خودکار مرورگر بعد از ۵ ثانیه
start "" cmd /c "timeout /t 5 >nul & start http://localhost:8000"

set PORT=8000
pazhoheshyar360-server.exe

echo.
echo سرور متوقف شد. (اگر خطا بود، پیام بالا را یادداشت کنید)
pause
