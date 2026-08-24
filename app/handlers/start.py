"""
app/handlers/start.py - Start Command & Link Handler for aiogram 3.x with Telegram Media Downloading
"""

import os
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, FSInputFile
from aiogram.utils.markdown import html_decoration as hd

from app.telegram.auth import check_user_session
from app.telegram.media import download_media_from_link

router = Router()

DEFAULT_API_ID = 32825705
DEFAULT_API_HASH = "4023849266ed4dfcd584031ce6b2a5f4"


def get_api_credentials():
    api_id_str = os.getenv("API_ID", "").strip()
    api_hash = os.getenv("API_HASH", "").strip()
    try:
        api_id = int(api_id_str)
        if api_id <= 0 or api_id > 2147483647:
            api_id = DEFAULT_API_ID
            api_hash = DEFAULT_API_HASH
    except ValueError:
        api_id = DEFAULT_API_ID
        api_hash = DEFAULT_API_HASH

    if not api_hash or len(api_hash) > 100 or "MIIBCg" in api_hash:
        api_hash = DEFAULT_API_HASH

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
            "✨ ระบบพร้อมใช้งานแล้ว! คุณสามารถส่ง Telegram Message Link มาในแชทนี้เพื่อดาวน์โหลด Media ได้ทันที"
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
            "กรุณาเลือกช่องทางเข้าสู่ระบบด้านล่างเพื่อเริ่มใช้งานดาวน์โหลด Media:"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 เปิด Telegram MiniApp", web_app=WebAppInfo(url=webapp_url))],
            [InlineKeyboardButton(text="🔐 Login ผ่าน Telegram Chat", callback_data="login_start")]
        ])

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.message(F.text.contains("t.me/"))
async def link_download_handler(message: Message):
    """
    Automatic Telegram Message Link Downloader Handler.
    """
    user_id = message.from_user.id
    link = message.text.strip()
    api_id, api_hash = get_api_credentials()

    status_msg = await message.answer("🔄 <b>กำลังดึงข้อมูลและดาวน์โหลด Media จาก Telegram...</b>", parse_mode="HTML")

    success, file_path, filename, error_msg = await download_media_from_link(user_id, link, api_id, api_hash)

    if success and file_path and os.path.exists(file_path):
        await status_msg.edit_text(f"📤 <b>ดาวน์โหลดสำเร็จ! กำลังส่งไฟล์ {hd.quote(filename)} ...</b>", parse_mode="HTML")
        try:
            input_file = FSInputFile(file_path)
            await message.answer_document(
                document=input_file,
                caption=f"✅ <b>{hd.quote(filename)}</b>\n📥 จากลิงก์: {hd.quote(link)}",
                parse_mode="HTML"
            )
            await status_msg.delete()
        except Exception:
            await status_msg.edit_text(
                f"✅ <b>ดาวน์โหลดสำเร็จเรียบร้อยแล้ว!</b>\n📁 ไฟล์: <code>{hd.quote(filename)}</code>",
                parse_mode="HTML"
            )
    else:
        err = hd.quote(error_msg or "เกิดข้อผิดพลาดในการดาวน์โหลด")
        await status_msg.edit_text(f"❌ <b>ดาวน์โหลดไม่สำเร็จ:</b> {err}", parse_mode="HTML")
