"""
app/telegram/media.py - Telethon Telegram Media Downloader Service (Quota Credit Enabled)
"""

import os
import re
import asyncio
import tempfile
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession

from app.telegram.auth import (
    get_user_session_string,
    validate_api_credentials,
    get_user_credits,
    deduct_user_credit
)


def parse_telegram_link(link: str):
    if not link:
        return None, None

    link = link.strip()
    
    # Format 1: Private channel/group -> https://t.me/c/1234567890/500
    m_private = re.search(r"t\.me/c/(\d+)/(\d+)", link)
    if m_private:
        channel_id = int(m_private.group(1))
        msg_id = int(m_private.group(2))
        peer_id = int(f"-100{channel_id}")
        return peer_id, msg_id

    # Format 2: Public channel/group -> https://t.me/channel_username/500
    m_public = re.search(r"t\.me/([a-zA-Z0-9_]+)/(\d+)", link)
    if m_public:
        username = m_public.group(1)
        msg_id = int(m_public.group(2))
        return username, msg_id

    return None, None


def get_downloads_dir() -> Path:
    if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        d = Path(tempfile.gettempdir()) / "telegram_downloads"
        d.mkdir(exist_ok=True)
        return d
    try:
        d = Path("downloads")
        d.mkdir(exist_ok=True)
        test_file = d / ".write_test"
        test_file.touch()
        test_file.unlink(missing_ok=True)
        return d
    except (OSError, PermissionError):
        d = Path(tempfile.gettempdir()) / "telegram_downloads"
        d.mkdir(exist_ok=True)
        return d


async def download_media_from_link(user_id: int, link: str, api_id: int, api_hash: str, progress_callback=None):
    """
    Download media from a Telegram message link using user's Telethon StringSession.
    Deducts 1 credit upon success.
    Returns: (success: bool, file_path: str, filename: str, error_msg: str)
    """
    # Check download credits first
    credits = get_user_credits(user_id)
    if credits <= 0:
        return False, None, None, "❌ โควตาดาวน์โหลดของคุณหมดแล้ว! (0 ครั้ง) กรุณาติดต่อแอดมินเพื่อเติมโควดาดาวน์โหลด"

    chat_entity, msg_id = parse_telegram_link(link)
    if not chat_entity or not msg_id:
        return False, None, None, "รูปแบบลิงก์ Telegram ไม่ถูกต้อง! ตัวอย่าง: https://t.me/c/123456789/100 หรือ https://t.me/channel/100"

    session_str = get_user_session_string(user_id)
    if not session_str:
        return False, None, None, "คุณยังไม่ได้เข้าสู่ระบบ Telegram Account กรุณา Login ในหน้า MiniApp หรือสั่ง /start เพื่อ Login ก่อน"

    api_id_int, api_hash_clean = validate_api_credentials(api_id, api_hash)
    client = TelegramClient(StringSession(session_str), api_id_int, api_hash_clean)
    try:
        await asyncio.wait_for(client.connect(), timeout=10.0)

        if not await client.is_user_authorized():
            return False, None, None, "Session Telegram ของคุณหมดอายุแล้ว กรุณา Login ใหม่"

        message = await asyncio.wait_for(client.get_messages(chat_entity, ids=msg_id), timeout=15.0)

        if not message:
            return False, None, None, "ไม่พบข้อความตามลิงก์ที่ระบุ (กรุณาตรวจสอบว่าบัญชีของคุณอยู่ในกลุ่ม/แชทนั้นหรือไม่)"

        if not message.media:
            return False, None, None, "ข้อความตามลิงก์ดังกล่าวไม่มีรูปภาพ วิดีโอ หรือไฟล์สื่อสำหรับดาวน์โหลด"

        downloads_dir = get_downloads_dir()
        file_path = await client.download_media(message, file=str(downloads_dir), progress_callback=progress_callback)
        
        if file_path and os.path.exists(file_path):
            filename = os.path.basename(file_path)
            
            # Deduct 1 credit upon successful download
            deduct_user_credit(user_id)
            
            return True, file_path, filename, None
        else:
            return False, None, None, "ดาวน์โหลดไฟล์ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง"

    except asyncio.TimeoutError:
        return False, None, None, "การดึงข้อมูลจาก Telegram หมดเวลา (Timeout) กรุณาลองใหม่อีกครั้ง"
    except Exception as e:
        return False, None, None, f"เกิดข้อผิดพลาดในการดาวน์โหลด: {str(e)}"
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
