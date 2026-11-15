#!/usr/bin/env bash
# =====================================================================
# استقرار پژوهشیار۳۶۰ روی سرور لینوکسی — پورت 8088
# اجرا:   sudo bash deploy/deploy.sh
# (این اسکریپت را داخل مخزن کلون‌شده اجرا کنید؛ اگر مخزن هنوز کلون نشده،
#  خودش در /opt/pazhoheshyar360 کلون می‌کند.)
# =====================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/pazhoheshyar360}"
REPO_URL="${REPO_URL:-https://github.com/hjalilvand2004-coder/pazhoheshyar.git}"
BRANCH="${BRANCH:-main}"
PORT="${PORT:-8088}"
RUN_USER="${RUN_USER:-pazhoheshyar360}"
SERVICE_NAME="pazhoheshyar360"
PUBLIC_IP="${PUBLIC_IP:-188.212.96.235}"

say() { printf '\033[1;36m▸ %s\033[0m\n' "$*"; }
ok()  { printf '\033[1;32m✔ %s\033[0m\n' "$*"; }
die() { printf '\033[1;31m✖ %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "این اسکریپت باید با sudo اجرا شود:  sudo bash deploy/deploy.sh"

# ---------- ۱) پیش‌نیازهای سیستمی
say "۱/۷ — بررسی پیش‌نیازها (python3, venv, git, curl)…"
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y >/dev/null
  DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip git curl >/dev/null
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y python3 python3-pip git curl >/dev/null
else
  command -v python3 >/dev/null 2>&1 || die "python3 یافت نشد — ابتدا پایتون ۳.۱۰+ را نصب کنید"
fi
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
  || die "پایتون ۳.۱۰ یا بالاتر لازم است (نسخه فعلی: $(python3 -V 2>&1))"

# ---------- ۲) دریافت / به‌روزرسانی مخزن
if [[ -d "$APP_DIR/.git" ]]; then
  say "۲/۷ — به‌روزرسانی مخزن موجود در $APP_DIR…"
  git -C "$APP_DIR" fetch --depth 1 origin "$BRANCH"
  git -C "$APP_DIR" reset --hard "origin/$BRANCH"
else
  say "۲/۷ — کلون مخزن در $APP_DIR…"
  mkdir -p "$APP_DIR"
  git clone --depth 1 -b "$BRANCH" "$REPO_URL" "$APP_DIR"
fi

# ---------- ۳) کاربر سرویس (بدون لاگین)
id -u "$RUN_USER" >/dev/null 2>&1 \
  || useradd --system --create-home --shell /usr/sbin/nologin "$RUN_USER"

# ---------- ۴) محیط مجازی و وابستگی‌ها
say "۴/۷ — ساخت محیط مجازی و نصب وابستگی‌ها…"
[[ -d "$APP_DIR/.venv" ]] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip -q
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt" -q

# ---------- ۵) پوشه‌های داده و مجوزها
say "۵/۷ — آماده‌سازی داده‌ها و مجوزها…"
mkdir -p "$APP_DIR/data" "$APP_DIR/uploads"
chown -R "$RUN_USER":"$RUN_USER" "$APP_DIR"

# ---------- ۶) سرویس systemd
say "۶/۷ — نصب و راه‌اندازی سرویس systemd ($SERVICE_NAME)…"
sed -e "s|__APP_DIR__|$APP_DIR|g" \
    -e "s|__RUN_USER__|$RUN_USER|g" \
    -e "s|__PORT__|$PORT|g" \
    "$APP_DIR/deploy/pazhoheshyar360.service" > "/etc/systemd/system/$SERVICE_NAME.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null 2>&1
systemctl restart "$SERVICE_NAME"

# ---------- ۷) تست سلامت
say "۷/۷ — تست سلامت روی پورت $PORT…"
UP=""
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/api/v1/services" >/dev/null 2>&1; then UP=yes; break; fi
  sleep 1
done
if [[ "$UP" != "yes" ]]; then
  journalctl -u "$SERVICE_NAME" -n 40 --no-pager || true
  die "سرویس بالا نیامد — لاگ بالا را بررسی کنید"
fi

# باز کردن پورت روی فایروال (اگر فعال باشد)
command -v ufw >/dev/null 2>&1 && ufw allow "$PORT/tcp" >/dev/null 2>&1 || true
command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --permanent --add-port="$PORT/tcp" >/dev/null 2>&1 && firewall-cmd --reload >/dev/null 2>&1 || true

ok "سامانه فعال است:  http://$PUBLIC_IP:$PORT"
cat <<EOF

============================================================
  پژوهشیار۳۶۰ روی پورت $PORT فعال شد ✔

  نشانی سامانه:      http://$PUBLIC_IP:$PORT
  تست سلامت:         http://$PUBLIC_IP:$PORT/api/v1/services
  مستندات API:       http://$PUBLIC_IP:$PORT/docs
  لاگ زندهٔ سرویس:   journalctl -u $SERVICE_NAME -f
  به‌روزرسانی بعدی:   sudo bash $APP_DIR/deploy/update.sh
  راهنمای کامل:      $APP_DIR/deploy/README-FA.md

  ▸ گام باقی‌ماندهٔ مهم — ثبت/فعال‌سازی کلاینت SSO روی پرتال:
    خطای «کلاینت ناشناس» یعنی client_id=pajouhyar360 هنوز در
    data/clients.json پرتال دانشجویار۳۶۰ (سمت پرتال، پورت 8086)
    ثبت و فعال نشده. اسنیپت آماده:
        $APP_DIR/deploy/portal-clients.json.snippet.json
    را مطابق راهنمای deploy/README-FA.md (بخش ۳) به پرتال اضافه
    کنید، سرویس پرتال را بازراه‌اندازی کنید و سامانه را در پنل
    مدیریت پرتال با همان client_id ثبت نمایید.
============================================================
EOF
