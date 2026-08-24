"""
app/handlers/start.py - Start Command Handler for aiogram 3.x with Telegram MiniApp & HTML Formatting
"""

import os
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.markdown import html_decoration as hd

from app.telegram.auth import check_user_session

router = Router()


def get_api_credentials():
    api_id_str = os.getenv("API_ID", "").strip()
    api_hash = os.getenv("API_HASH", "").strip()
    try:
        api_id = int(api_id_str)
    except ValueError:
        api_id = 0
    return api_id, api_hash


def get_webapp_url():
    return os.getenv("WEBAPP_URL", "https://telegram-downloader-nggk.vercel.app/miniapp").strip()


@router.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    Handler for /start command - Displays status, Chat Login, and Telegram MiniApp.
    """
    user_id = message.from_user.id
    raw_user_name = message.from_user.full_name if message.from_user else "User"
    user_name = hd.quote(raw_user_name)
    
    api_id, api_hash = get_api_credentials()
    webapp_url = get_webapp_url()

    session_info = await check_user_session(user_id, api_id, api_hash)

    if session_info.get("connected"):
        username = hd.quote(session_info.get("username", user_name))
        text = (
            f"👋 <b>สวัสดีครับคุณ {user_name}!</b>\n\n"
            "🤖 <b>ยินดีต้อนรับสู่ Telegram Downloader MiniApp</b>\n\n"
            f"🟢 <b>Telegram Account:</b> Connected (<code>{username}</code>)\n"
            f"📱 <b>Telegram ID:</b> <code>{user_id}</code>\n\n"
            "✨ ระบบพร้อมใช้งานแล้ว! กดปุ่มเปิด MiniApp หรือส่ง Telegram Message Link มาในแชทนี้เพื่อดาวน์โหลด Media ได้ทันที"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 เปิด Telegram MiniApp", web_app=WebAppInfo(url=webapp_url))],
            [InlineKeyboardButton(text="🔗 วิธีส่ง Telegram Link", callback_data="send_link_info")],
            [InlineKeyboardButton(text="🔓 Logout", callback_data="logout")]
        ])
    else:
        text = (
            f"👋 <b>สวัสดีครับคุณ {user_name}!</b>\n\n"
            "🤖 <b>ยินดีต้อนรับสู่ Telegram Downloader MiniApp</b>\n\n"
            "🔴 <b>Telegram Account:</b> Not Connected\n\n"
            "กรุณาเลือกช่องทางเข้าสู่ระบบด้านล่าง:"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 เปิด Telegram MiniApp", web_app=WebAppInfo(url=webapp_url))],
            [InlineKeyboardButton(text="🔐 Login ผ่าน Telegram Chat", callback_data="login_start")]
        ])

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
