"""نقطه ورود سرور پژوهشیار۳۶۰ — قابل استفاده مستقیم با پایتون یا داخل بسته PyInstaller"""
import os

if __name__ == "__main__":
    # در حالت PyInstaller، آبجکت اپ مستقیم پاس داده می‌شود (import string در بسته فریز‌شده شکننده است)
    try:
        from app.main import app
        target = app
    except ImportError:
        import uvicorn
        uvicorn.run("app.main:app", host=os.environ.get("HOST", "0.0.0.0"),
                    port=int(os.environ.get("PORT", "8000")), log_level="info")
    else:
        import uvicorn
        uvicorn.run(target, host=os.environ.get("HOST", "0.0.0.0"),
                    port=int(os.environ.get("PORT", "8000")), log_level="info")
