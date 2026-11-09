#!/usr/bin/env bash
# ساخت نسخه اجرایی مستقل (بدون نیاز به پایتون روی سیستم مقصد) — لینوکس/مک
set -e
cd "$(dirname "$0")/.."
echo "==> 1/4 ساخت فرانت React"
(cd frontend && npm ci --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund) && (cd frontend && npm run build)
echo "==> 2/4 نصب وابستگی‌های بک‌اند + PyInstaller"
cd backend && python3 -m pip install -r requirements-build.txt
echo "==> 3/4 بسته‌بندی با PyInstaller"
python3 -m PyInstaller PazhoheshYar.spec --noconfirm
echo "==> 4/4 اتمام"
echo "فایل اجرایی: backend/dist/pazhoheshyar360-server"
echo "اجرا: ./dist/pazhoheshyar360-server  سپس مرورگر: http://localhost:8000"
