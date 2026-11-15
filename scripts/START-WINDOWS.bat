@echo off
REM اجرای بسته مستقل پژوهشیار۳۶۰ روی ویندوز — به پایتون نیازی نیست
REM پورت: متغیر محیطی PORT اگر ست شده باشد respected است؛ پیش‌فرض 8088 (استقرار تولیدی)
chcp 65001 >nul
title Pazhoheshyar360 Server
cd /d "%~dp0"

REM پورت اجرا — با متغیر محیطی PORT قابل تغییر است (در PowerShell:  $env:PORT="8090")
if not defined PORT set PORT=8088

echo ============================================
echo   پژوهشیار۳۶۰ - نسخه اجرایی مستقل
echo   آدرس محلی:  http://localhost:%PORT%
echo   آدرس سرور:  http://188.212.96.235:%PORT%
echo ============================================

REM اگر پورت اشغال باشد سرور بالا نمی‌آید (خطای 10048) — از قبل هشدار بده
netstat -ano | findstr /C:":%PORT% " | findstr /C:"LISTENING" >nul
if not errorlevel 1 (
  echo.
  echo  [خطا] پورت %PORT% اشغال است و سرور نمی‌تواند گوش دهد.
  echo        یا سرویس دیگر را متوقف کنید یا پورت دیگری بدهید؛ در PowerShell:
  echo            $env:PORT="8090"
  echo            .\START-WINDOWS.bat
  echo        پردازش اشغال‌کننده:  netstat -ano ^| findstr ":%PORT%"
  echo.
  pause
  exit /b 1
)

echo سرور در حال روشن شدن است...

REM باز کردن خودکار مرورگر بعد از ۵ ثانیه
start "" cmd /c "timeout /t 5 >nul & start http://localhost:%PORT%"

pazhoheshyar360-server.exe

echo.
echo سرور متوقف شد. (اگر خطا بود، پیام بالا را یادداشت کنید)
pause
