#!/usr/bin/env bash
# اجرای پژوهشیار۳۶۰ — نسخه اجرایی مستقل لینوکس (بدون نیاز به پایتون)
# استفاده:  bash START-LINUX.sh            → پورت پیش‌فرض 8088
#           PORT=8080 bash START-LINUX.sh  → پورت دلخواه
cd "$(dirname "$0")" || exit 1
PORT="${PORT:-8088}"
export PORT
chmod +x ./pazhoheshyar360-server 2>/dev/null || true

echo "============================================"
echo "  پژوهشیار۳۶۰ — نسخه اجرایی مستقل (لینوکس)"
echo "  آدرس محلی: http://localhost:$PORT"
echo "============================================"

# اگر پورت اشغال باشد سرور بالا نمی‌آید — از قبل هشدار بده (اگر ابزار موجود بود)
BUSY=""
if command -v ss >/dev/null 2>&1; then
  ss -ltn 2>/dev/null | grep -q ":$PORT " && BUSY=1
elif command -v netstat >/dev/null 2>&1; then
  netstat -ltn 2>/dev/null | grep -q ":$PORT " && BUSY=1
fi
if [ -n "$BUSY" ]; then
  echo "  [خطا] پورت $PORT اشغال است؛ سرویس دیگری روی آن گوش می‌دهد."
  echo "        پورت دیگر:  PORT=8090 bash START-LINUX.sh"
  echo "        پردازش اشغال‌کننده:  ss -ltnp | grep :$PORT"
  exit 1
fi

echo "  سرور در حال روشن شدن است..."
exec ./pazhoheshyar360-server
