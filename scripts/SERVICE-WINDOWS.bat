@echo off
REM اجرای بدون‌سر‌وصدا برای شروع خودکار (Task Scheduler / سرویس) — بدون مرورگر و بدون pause
REM خروجی و لاگ در server-log.txt کنار همین فایل نوشته می‌شود.
REM ثبت شروع خودکار (به‌جای مسیر، مسیر واقعی نصب را بگذارید):
REM   schtasks /Create /TN "Pazhoheshyar360" /SC ONSTART /RU SYSTEM /RL HIGHEST /TR "C:\pazhoheshyar360\SERVICE-WINDOWS.bat"
chcp 65001 >nul
cd /d "%~dp0"
if not defined PORT set PORT=8088
set HOST=0.0.0.0
echo [%date% %time%] pazhoheshyar360 starting on port %PORT% >> server-log.txt
pazhoheshyar360-server.exe >> server-log.txt 2>&1
echo [%date% %time%] pazhoheshyar360 exited with code %errorlevel% >> server-log.txt
