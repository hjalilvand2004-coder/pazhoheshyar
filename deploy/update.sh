#!/usr/bin/env bash
# =====================================================================
# به‌روزرسانی پژوهشیار۳۶۰ روی سرور — آخرین نسخهٔ main + ری‌استارت سرویس
# اجرا:   sudo bash deploy/update.sh
# =====================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/pazhoheshyar360}"
BRANCH="${BRANCH:-main}"
SERVICE_NAME="pazhoheshyar360"
PORT="${PORT:-8088}"
PUBLIC_IP="${PUBLIC_IP:-188.212.96.235}"

say() { printf '\033[1;36m▸ %s\033[0m\n' "$*"; }
ok()  { printf '\033[1;32m✔ %s\033[0m\n' "$*"; }
die() { printf '\033[1;31m✖ %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "این اسکریپت باید با sudo اجرا شود:  sudo bash deploy/update.sh"
[[ -d "$APP_DIR/.git" ]] || die "مخزن در $APP_DIR یافت نشد — ابتدا deploy.sh را اجرا کنید"

say "دریافت آخرین نسخهٔ $BRANCH…"
git -C "$APP_DIR" fetch --depth 1 origin "$BRANCH"
git -C "$APP_DIR" reset --hard "origin/$BRANCH"

say "به‌روزرسانی وابستگی‌ها…"
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt" -q

say "ری‌استارت سرویس…"
systemctl restart "$SERVICE_NAME"

UP=""
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/api/v1/services" >/dev/null 2>&1; then UP=yes; break; fi
  sleep 1
done
[[ "$UP" == "yes" ]] || { journalctl -u "$SERVICE_NAME" -n 40 --no-pager || true; die "سرویس بعد از به‌روزرسانی بالا نیامد"; }

echo
ok "به‌روزرسانی انجام شد — HEAD: $(git -C "$APP_DIR" rev-parse --short HEAD)"
ok "سامانه فعال است:  http://$PUBLIC_IP:$PORT"
