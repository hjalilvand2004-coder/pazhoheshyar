"""نقطه ورود سرور پژوهشیار۳۶۰ — قابل استفاده مستقیم با پایتون یا داخل بسته PyInstaller"""
import os
import socket
import threading
import time
import webbrowser

DEFAULT_PORT = 8088


def _open_browser_when_ready(host: str, port: int, timeout_s: int = 90) -> None:
    """منتظر بالا آمدن سرور می‌ماند و بعد مرورگر را باز می‌کند — خطاها را نادیده می‌گیرد."""
    target = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    url = f"http://localhost:{port}/" if target == "127.0.0.1" else f"http://{target}:{port}/"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection((target, port), timeout=1.0):
                break
        except OSError:
            time.sleep(0.5)
    else:
        return  # سرور در مهلت مقرر بالا نیامد — مرورگری باز نمی‌کنیم
    time.sleep(0.8)  # چند دهم ثانیه تا uvicorn کاملاً آماده پاسخ‌دهی شود
    try:
        webbrowser.open(url)
    except Exception:
        pass


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", str(DEFAULT_PORT)))
    print("=" * 58, flush=True)
    print("  Pazhoheshyar360 v1.4.0", flush=True)
    print(f"  URL:      http://localhost:{port}", flush=True)
    print("  Demo:     student1 / prof1 / manager1 / admin1", flush=True)
    print("            (password for all: 12345678)", flush=True)
    print("  Stop:     close this window (or press Ctrl+C)", flush=True)
    print("  Browser opens automatically when the server is ready.", flush=True)
    print("=" * 58, flush=True)
    # مرورگر خودکار — با NO_BROWSER=1 غیرفعال می‌شود (مثلاً روی سرور بدون دسکتاپ)
    if os.environ.get("NO_BROWSER", "").strip().lower() not in ("1", "true", "yes"):
        threading.Thread(target=_open_browser_when_ready, args=(host, port), daemon=True).start()
    # در حالت PyInstaller، آبجکت اپ مستقیم پاس داده می‌شود (import string در بسته فریز‌شده شکننده است)
    try:
        from app.main import app
        target = app
    except ImportError:
        import uvicorn
        uvicorn.run("app.main:app", host=host, port=port, log_level="info")
    else:
        import uvicorn
        uvicorn.run(target, host=host, port=port, log_level="info")
