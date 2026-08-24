"""
bot.py - Telegram Bot Entry Point (aiogram 3.x)
Telegram Downloader Bot & MiniApp Launcher
"""

import os
import sys
import asyncio
from pathlib import Path

# Load environment variables from .env
def load_env(env_file=".env"):
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_env()

try:
    from aiogram import Bot, Dispatcher
    from aiogram.enums import ParseMode
    from aiogram.client.default import DefaultBotProperties
    from aiogram.types import MenuButtonWebApp, WebAppInfo
    HAS_AIOGRAM = True
except ImportError:
    HAS_AIOGRAM = False


async def start_bot_async():
    if not HAS_AIOGRAM:
        print("[ERROR] aiogram is not installed! Please run: pip install aiogram telethon")
        return

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token or bot_token == "ใส่_token_ของ_bot":
        print("[ERROR] BOT_TOKEN is missing or not configured in .env!")
        return

    webapp_url = os.getenv("WEBAPP_URL", "http://localhost:8000/miniapp").strip()

    # Initialize Bot & Dispatcher with ParseMode.HTML
    bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Include routers
    try:
        from app.handlers import start_router, login_router
        dp.include_router(start_router)
        dp.include_router(login_router)
    except Exception as e:
        print(f"[WARNING] Failed to load handlers: {e}")

    try:
        me = await bot.get_me()
        print(f"[INFO] Telegram Bot connected: @{me.username}")
        
        # Set Telegram Menu Button to open MiniApp
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="📱 เปิด MiniApp",
                    web_app=WebAppInfo(url=webapp_url)
                )
            )
            print(f"[INFO] Telegram Menu Button configured: {webapp_url}")
        except Exception as e:
            print(f"[NOTICE] Could not set menu button (URL must be HTTPS for official Telegram menu button): {e}")

        print(f"[INFO] Telegram Bot polling started")
        
        # Delete any leftover webhook before starting polling
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        print(f"[ERROR] Failed during bot execution: {e}")
    finally:
        await bot.session.close()


def start_bot():
    """Main entry point to run Telegram bot polling."""
    if not HAS_AIOGRAM:
        print("[ERROR] aiogram 3.x is not installed. Please install it using: pip install aiogram telethon")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(start_bot_async())
    except KeyboardInterrupt:
        print("\n[INFO] Telegram Bot stopped by user.")

if __name__ == "__main__":
    start_bot()
