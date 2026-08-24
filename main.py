"""
main.py - Main Entry Point
Telegram Downloader Application
"""

import os
import sys
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

def check_environment():
    """Verify directories and configuration."""
    base_dir = Path(__file__).parent.resolve()
    
    # Create required directories if missing
    downloads_dir = base_dir / "downloads"
    sessions_dir = base_dir / "sessions"
    downloads_dir.mkdir(exist_ok=True)
    sessions_dir.mkdir(exist_ok=True)

    # Check .env file
    env_file = base_dir / ".env"
    if not env_file.exists():
        print("[WARNING] .env file not found! Creating default .env from .env.example if available.")
        env_example = base_dir / ".env.example"
        if env_example.exists() and env_example.stat().st_size > 0:
            env_file.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")

    load_env(str(env_file))

    bot_token = os.getenv("BOT_TOKEN", "")
    api_id = os.getenv("API_ID", "")
    api_hash = os.getenv("API_HASH", "")

    print(f"[INFO] Workspace: {base_dir}")
    print(f"[INFO] Downloads folder: {downloads_dir}")
    print(f"[INFO] Sessions folder: {sessions_dir}")
    print(f"[INFO] BOT_TOKEN status: {'Configured' if bot_token and bot_token != 'ใส่_token_ของ_bot' else 'Needs Configuration'}")
    print(f"[INFO] API_ID status: {'Configured' if api_id and api_id != 'ใส่_api_id' else 'Needs Configuration'}")
    print(f"[INFO] API_HASH status: {'Configured' if api_hash and api_hash != 'ใส่_api_hash' else 'Needs Configuration'}")

def main():
    """Main application launcher."""
    print("=" * 60)
    print("          Telegram Downloader System Startup")
    print("=" * 60)

    check_environment()

    print("-" * 60)
    print("[INFO] Launching Telegram Downloader services...")
    
    try:
        run_path = Path(__file__).parent / "run.py"
        spec = importlib.util.spec_from_file_location("run_file_module", str(run_path))
        if spec and spec.loader:
            run_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(run_module)
            run_all_func = getattr(run_module, "run_all", None)
            if run_all_func:
                run_all_func()
            else:
                print("[ERROR] Function run_all not found in run.py")
    except KeyboardInterrupt:
        print("\n[INFO] Application stopped by user.")
    except Exception as e:
        print(f"[ERROR] Unexpected error while running application: {e}")

if __name__ == "__main__":
    main()
