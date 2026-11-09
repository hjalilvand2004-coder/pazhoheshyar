"""نقطه ورود سرور پژوهشیار۳۶۰ — قابل استفاده مستقیم با پایتون یا داخل بسته PyInstaller"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("app.main:app", host=host, port=port, log_level="info")
