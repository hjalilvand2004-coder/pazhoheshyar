#!/usr/bin/env bash
# اجرای ساده با پایتون (سیستم‌هایی که پایتون دارند)
set -e
cd "$(dirname "$0")/.."
if [ ! -d frontend/dist ]; then
  echo "فرانت ساخته نشده؛ ابتدا: (cd frontend && npm install && npm run build)"
  exit 1
fi
cd backend
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -q -r requirements.txt
exec python run.py
