"""
run.py - Service Launcher
Launcher for Telegram Bot and FastAPI server
"""

import os
import sys
import time
import threading
import asyncio
import importlib.util
from pathlib import Path

# Load environment variables
def load_env(env_file=".env"):
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_env()

def get_fastapi_app():
    """Load FastAPI application instance from app.py safely."""
    app_path = Path(__file__).parent / "app.py"
    if not app_path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("app_file_module", str(app_path))
        if spec and spec.loader:
            app_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_module)
            return getattr(app_module, "app", None)
    except Exception as e:
        print(f"[ERROR] Failed to load app.py: {e}")
    return None

def start_fastapi_server(host="0.0.0.0", port=8000):
    """Run FastAPI application."""
    try:
        import uvicorn
        fastapi_app = get_fastapi_app()
        if fastapi_app is not None:
            print(f"[INFO] Starting FastAPI server on http://{host}:{port}")
            uvicorn.run(fastapi_app, host=host, port=port, log_level="warning")
        else:
            print("[WARNING] FastAPI 'app' instance could not be loaded from app.py.")
    except ImportError:
        print("[WARNING] uvicorn is not installed. FastAPI server will not start.")
    except Exception as e:
        print(f"[ERROR] Failed to start FastAPI server: {e}")

def start_telegram_bot_service():
    """Run Telegram Bot service via start_bot()."""
    try:
        bot_path = Path(__file__).parent / "bot.py"
        spec = importlib.util.spec_from_file_location("bot_file_module", str(bot_path))
        if spec and spec.loader:
            bot_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(bot_module)
            start_bot_func = getattr(bot_module, "start_bot", None)
            if start_bot_func:
                start_bot_func()
            else:
                print("[ERROR] Function start_bot not found in bot.py")
    except Exception as e:
        print(f"[ERROR] Failed to start Telegram Bot: {e}")

def run_all(host="0.0.0.0", port=8000):
    """Launch both FastAPI server and Telegram Bot concurrently."""
    print("=" * 50)
    print("      Telegram Downloader Launcher")
    print("=" * 50)

    # Ensure required directories exist
    Path("downloads").mkdir(exist_ok=True)
    Path("sessions").mkdir(exist_ok=True)

    # Start FastAPI in a background daemon thread
    web_thread = threading.Thread(
        target=start_fastapi_server,
        kwargs={"host": host, "port": port},
        daemon=True
    )
    web_thread.start()

    # Small pause to let server initialize
    time.sleep(1)

    # Start Telegram Bot in main thread (blocks and runs aiogram polling)
    start_telegram_bot_service()

if __name__ == "__main__":
    run_all()
