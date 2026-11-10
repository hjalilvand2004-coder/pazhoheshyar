@echo off
REM ============================================================
REM  پژوهشیار۳۶۰ — ساخت بسته اجرایی مستقل ویندوز (بدون نیاز به پایتون در سیستم مقصد)
REM  پیش‌نیاز سیستمِ ساخت: Python 3.10+ و (اختیاری) Node.js 18+
REM  اجرا: دابل‌کلیک روی همین فایل  یا  از cmd:  scripts\build_portable.bat
REM  خروجی:  dist\Pazhoheshyar360-Windows\  و فایل zip آماده انتقال
REM ============================================================
setlocal enabledelayedexpansion
chcp 65001 >nul
title Build Pazhoheshyar360 - Windows Portable

cd /d "%~dp0.." || goto :err
set "ROOT=%cd%"

echo ==^> [1/5] بررسی پیش‌نیازها
where python >nul 2>nul
if errorlevel 1 (
  echo    [خطا] Python پیدا نشد. Python 3.10 یا جدیدتر را نصب و به PATH اضافه کنید.
  goto :err
)
for /f "tokens=*" %%i in ('python -c "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set PYVER=%%i
if not defined PYVER (
  echo    [خطا] python اجرا نشد. اگر ویندوز فروشگاه را باز کرد، Python را از python.org نصب کنید
  echo    و هنگام نصب گزینه "Add python.exe to PATH" را فعال کنید.
  goto :err
)
echo    Python !PYVER! پیدا شد.

echo ==^> [2/5] ساخت فرانت‌اند React
if exist "frontend\dist\index.html" (
  echo    frontend\dist از قبل موجود است - از نسخه فعلی استفاده می‌شود.
) else (
  where npm >nul 2>nul
  if errorlevel 1 (
    echo    [خطا] نه frontend\dist موجود است و نه Node.js/npm برای ساخت آن.
    echo    یا Node.js را نصب کنید یا پوشه frontend\dist را از مخزن دریافت کنید.
    goto :err
  )
  pushd frontend
  call npm install --no-audit --no-fund || goto :npmfail
  call npm run build || goto :npmfail
  popd
)

echo ==^> [3/5] نصب وابستگی‌های بک‌اند و PyInstaller
python -m pip install --upgrade pip >nul || goto :err
python -m pip install -r "backend\requirements-build.txt" || goto :err

echo ==^> [4/5] بسته‌بندی با PyInstaller (تک‌فایل)
pushd backend
python -m PyInstaller PazhoheshYar.spec --noconfirm --clean || goto :pyfail
popd
if not exist "backend\dist\pazhoheshyar360-server.exe" (
  echo    [خطا] فایل اجرایی ساخته نشد.
  goto :err
)

echo ==^> [5/5] ساخت پوشه بسته قابل انتقال
set "PKG=%ROOT%\dist\Pazhoheshyar360-Windows"
if exist "%PKG%" rmdir /s /q "%PKG%"
mkdir "%PKG%" || goto :err
copy /y "backend\dist\pazhoheshyar360-server.exe" "%PKG%\" >nul || goto :err
copy /y "%ROOT%\scripts\START-WINDOWS.bat" "%PKG%\" >nul || goto :err
copy /y "%ROOT%\README.md" "%PKG%\" >nul 2>nul
(
  echo پژوهشیار۳۶۰ - نسخه اجرایی مستقل ویندوز
  echo ========================================
  echo ۱. روی START-WINDOWS.bat دابل‌کلیک کنید ^(یا خود فایل pazhoheshyar360-server.exe^).
  echo ۲. در مرورگر آدرس http://localhost:8000 را باز کنید.
  echo ۳. حساب‌های آزمایشی: student1 / prof1 / manager1 / admin1  - رمز همه: 12345678
  echo ۴. داده‌ها در پوشه data کنار همین فایل‌ها ذخیره می‌شود؛ برای انتقال کامل، کل پوشه را کپی کنید.
  echo ۵. پورت پیش‌فرض 8000 است؛ برای تغییر:  set PORT=8080  سپس اجرای فایل exe.
  echo.
  echo ورود یکپارچه ^(SSO^): از منوی مدیریت ^> تنظیمات SSO، مقادیر Keycloak را وارد و فعال کنید.
) > "%PKG%\راهنمای-اجرا.txt"
powershell -NoProfile -Command "Compress-Archive -Path '%PKG%' -DestinationPath '%ROOT%\dist\Pazhoheshyar360-Windows.zip' -Force" || goto :err

echo.
echo ============================================================
echo   بسته آماده است:
echo     %PKG%
echo     %ROOT%\dist\Pazhoheshyar360-Windows.zip
echo   این پوشه/zip را به هر ویندوزی ببرید - به پایتون نیازی نیست.
echo ============================================================
if not defined CI pause
exit /b 0

:npmfail
popd
echo    [خطا] ساخت فرانت با npm ناموفق بود.
goto :err
:pyfail
popd
echo    [خطا] PyInstaller ناموفق بود.
:err
echo.
echo ساخت بسته متوقف شد. پیام بالا را بررسی کنید.
if not defined CI pause
exit /b 1
