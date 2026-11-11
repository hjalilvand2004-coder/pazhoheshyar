#!/usr/bin/env bash
# اجرای پژوهشیار۳۶۰ — نسخه اجرایی مستقل لینوکس (بدون نیاز به پایتون)
# استفاده:  bash START-LINUX.sh          → پورت پیش‌فرض 8000
#           PORT=8080 bash START-LINUX.sh → پورت دلخواه
cd "$(dirname "$0")" || exit 1
PORT="${PORT:-8000}"
export PORT
chmod +x ./pazhoheshyar360-server 2>/dev/null || true
echo "============================================"
echo "  پژوهشیار۳۶۰ — نسخه اجرایی مستقل (لینوکس)"
echo "  سرور در حال روشن شدن است..."
echo "  آدرس: http://localhost:$PORT"
echo "============================================"
exec ./pazhoheshyar360-server
