"""
app/telegram/auth.py - Telethon User Authentication Service (Vercel Read-Only FS Safe)
"""

import os
import tempfile
from pathlib import Path
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError


def get_sessions_dir() -> Path:
    """Returns writable sessions directory (falls back to /tmp for Vercel/Lambda)."""
    try:
        d = Path("sessions")
        d.mkdir(exist_ok=True)
        return d
    except (OSError, PermissionError):
        d = Path(tempfile.gettempdir()) / "telegram_sessions"
        d.mkdir(exist_ok=True)
        return d


def get_user_session_path(user_id: int) -> str:
    """Returns the file path for user's Telethon session (without .session extension)."""
    sessions_dir = get_sessions_dir()
    return str(sessions_dir / f"telegram_user_{user_id}")


def get_session_file(user_id: int) -> Path:
    """Returns Path object for user's session file."""
    sessions_dir = get_sessions_dir()
    return sessions_dir / f"telegram_user_{user_id}.session"


def is_user_logged_in(user_id: int) -> bool:
    """Check if session file exists for user."""
    session_file = get_session_file(user_id)
    return session_file.exists() and session_file.stat().st_size > 0


async def check_user_session(user_id: int, api_id: int, api_hash: str) -> dict:
    """
    Check if the user session is active and valid.
    Returns info dict: {"connected": True/False, "username": "...", "id": ...}
    """
    try:
        api_id = int(api_id)
    except (ValueError, TypeError):
        return {"connected": False, "error": "invalid_api_id"}

    session_file = get_session_file(user_id)
    if not session_file.exists():
        return {"connected": False}

    session_path = get_user_session_path(user_id)
    client = TelegramClient(session_path, api_id, api_hash)
    try:
        await client.connect()
        if await client.is_user_authorized():
            me = await client.get_me()
            username = f"@{me.username}" if me and me.username else (me.first_name if me else f"ID: {user_id}")
            return {
                "connected": True,
                "username": username,
                "id": me.id if me else user_id
            }
        else:
            return {"connected": False}
    except Exception:
        return {"connected": False}
    finally:
        await client.disconnect()


async def send_otp(user_id: int, phone_number: str, api_id: int, api_hash: str):
    """
    Send OTP code to user's Telegram account using Telethon.
    Returns: (success: bool, phone_code_hash: str, error_message: str)
    """
    try:
        api_id = int(api_id)
    except (ValueError, TypeError):
        return False, None, "API_ID ต้องเป็นตัวเลข"

    session_path = get_user_session_path(user_id)
    client = TelegramClient(session_path, api_id, api_hash)
    try:
        await client.connect()
        res = await client.send_code_request(phone_number)
        return True, res.phone_code_hash, None
    except Exception as e:
        return False, None, str(e)
    finally:
        await client.disconnect()


async def verify_otp(user_id: int, phone_number: str, phone_code_hash: str, code: str, api_id: int, api_hash: str):
    """
    Verify the OTP code entered by user.
    Returns: (status: str ["SUCCESS", "NEED_2FA", "INVALID_CODE", "ERROR"], user_info: dict, error_msg: str)
    """
    try:
        api_id = int(api_id)
    except (ValueError, TypeError):
        return "ERROR", None, "API_ID ต้องเป็นตัวเลข"

    session_path = get_user_session_path(user_id)
    client = TelegramClient(session_path, api_id, api_hash)
    try:
        await client.connect()
        try:
            await client.sign_in(phone=phone_number, code=code, phone_code_hash=phone_code_hash)
            me = await client.get_me()
            username = f"@{me.username}" if me and me.username else (me.first_name if me else f"ID: {user_id}")
            return "SUCCESS", {"username": username, "id": me.id}, None
        except SessionPasswordNeededError:
            return "NEED_2FA", None, None
        except PhoneCodeInvalidError:
            return "INVALID_CODE", None, "รหัส OTP ไม่ถูกต้อง กรุณาตรวจสอบรหัสอีกครั้ง"
        except PhoneCodeExpiredError:
            return "ERROR", None, "รหัส OTP หมดอายุแล้ว กรุณาเริ่มใหม่อีกครั้ง"
    except Exception as e:
        return "ERROR", None, str(e)
    finally:
        await client.disconnect()


async def verify_2fa(user_id: int, password: str, api_id: int, api_hash: str):
    """
    Verify 2FA password.
    Returns: (success: bool, user_info: dict, error_msg: str)
    """
    try:
        api_id = int(api_id)
    except (ValueError, TypeError):
        return False, None, "API_ID ต้องเป็นตัวเลข"

    session_path = get_user_session_path(user_id)
    client = TelegramClient(session_path, api_id, api_hash)
    try:
        await client.connect()
        await client.sign_in(password=password)
        me = await client.get_me()
        username = f"@{me.username}" if me and me.username else (me.first_name if me else f"ID: {user_id}")
        return True, {"username": username, "id": me.id}, None
    except Exception as e:
        return False, None, str(e)
    finally:
        await client.disconnect()


async def logout_user(user_id: int, api_id: int, api_hash: str) -> bool:
    """Log out and remove user's session file."""
    try:
        api_id = int(api_id)
    except (ValueError, TypeError):
        api_id = 0

    session_path = get_user_session_path(user_id)
    session_file = get_session_file(user_id)
    if session_file.exists():
        client = TelegramClient(session_path, api_id, api_hash)
        try:
            await client.connect()
            if await client.is_user_authorized():
                await client.log_out()
        except Exception:
            pass
        finally:
            await client.disconnect()

        try:
            if session_file.exists():
                os.remove(session_file)
        except Exception:
            pass
        return True
    return False
