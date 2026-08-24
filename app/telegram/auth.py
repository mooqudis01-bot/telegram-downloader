"""
app/telegram/auth.py - Telethon User Authentication Service (Vercel Writable FS Safe & Int32 Safe)
"""

import os
import asyncio
import tempfile
from pathlib import Path
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError

DEFAULT_API_ID = 32825705
DEFAULT_API_HASH = "4023849266ed4dfcd584031ce6b2a5f4"


def get_sessions_dir() -> Path:
    """Returns writable sessions directory (always uses /tmp on Vercel/Lambda)."""
    if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        d = Path(tempfile.gettempdir()) / "telegram_sessions"
        d.mkdir(exist_ok=True)
        return d

    try:
        d = Path("sessions")
        d.mkdir(exist_ok=True)
        test_file = d / ".write_test"
        test_file.touch()
        test_file.unlink(missing_ok=True)
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


def validate_api_credentials(api_id: int, api_hash: str):
    """Validate that API_ID fits 32-bit signed int and API_HASH is clean, with fallback."""
    try:
        api_id_int = int(api_id)
        if api_id_int <= 0 or api_id_int > 2147483647:
            api_id_int = DEFAULT_API_ID
            api_hash = DEFAULT_API_HASH
    except (ValueError, TypeError):
        api_id_int = DEFAULT_API_ID
        api_hash = DEFAULT_API_HASH

    if not api_hash or len(api_hash) > 100 or "MIIBCg" in api_hash:
        api_hash = DEFAULT_API_HASH

    return api_id_int, api_hash


def is_user_logged_in(user_id: int) -> bool:
    """Check if session file exists for user."""
    session_file = get_session_file(user_id)
    return session_file.exists() and session_file.stat().st_size > 0


async def check_user_session(user_id: int, api_id: int, api_hash: str) -> dict:
    """
    Check if the user session is active and valid.
    Returns info dict: {"connected": True/False, "username": "...", "id": ...}
    """
    api_id_int, api_hash_clean = validate_api_credentials(api_id, api_hash)

    session_file = get_session_file(user_id)
    if not session_file.exists():
        return {"connected": False}

    session_path = get_user_session_path(user_id)
    client = TelegramClient(session_path, api_id_int, api_hash_clean)
    try:
        await asyncio.wait_for(client.connect(), timeout=6.0)
        if await asyncio.wait_for(client.is_user_authorized(), timeout=6.0):
            me = await asyncio.wait_for(client.get_me(), timeout=6.0)
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
        try:
            await client.disconnect()
        except Exception:
            pass


async def send_otp(user_id: int, phone_number: str, api_id: int, api_hash: str):
    """
    Send OTP code to user's Telegram account using Telethon.
    Returns: (success: bool, phone_code_hash: str, error_message: str)
    """
    api_id_int, api_hash_clean = validate_api_credentials(api_id, api_hash)
    phone_clean = phone_number.strip().replace(" ", "").replace("-", "")

    session_path = get_user_session_path(user_id)
    client = TelegramClient(session_path, api_id_int, api_hash_clean)
    try:
        await asyncio.wait_for(client.connect(), timeout=8.0)
        res = await asyncio.wait_for(client.send_code_request(phone_clean), timeout=10.0)
        return True, res.phone_code_hash, None
    except asyncio.TimeoutError:
        return False, None, "การเชื่อมต่อ Telegram หมดเวลา (Timeout) กรุณาลองใหม่อีกครั้ง"
    except Exception as e:
        return False, None, str(e)
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def verify_otp(user_id: int, phone_number: str, phone_code_hash: str, code: str, api_id: int, api_hash: str):
    """
    Verify the OTP code entered by user.
    Returns: (status: str ["SUCCESS", "NEED_2FA", "INVALID_CODE", "ERROR"], user_info: dict, error_msg: str)
    """
    api_id_int, api_hash_clean = validate_api_credentials(api_id, api_hash)
    phone_clean = phone_number.strip().replace(" ", "").replace("-", "")

    session_path = get_user_session_path(user_id)
    client = TelegramClient(session_path, api_id_int, api_hash_clean)
    try:
        await asyncio.wait_for(client.connect(), timeout=8.0)
        try:
            await asyncio.wait_for(client.sign_in(phone=phone_clean, code=code, phone_code_hash=phone_code_hash), timeout=10.0)
            me = await asyncio.wait_for(client.get_me(), timeout=6.0)
            username = f"@{me.username}" if me and me.username else (me.first_name if me else f"ID: {user_id}")
            return "SUCCESS", {"username": username, "id": me.id}, None
        except SessionPasswordNeededError:
            return "NEED_2FA", None, None
        except PhoneCodeInvalidError:
            return "INVALID_CODE", None, "รหัส OTP ไม่ถูกต้อง กรุณาตรวจสอบรหัสอีกครั้ง"
        except PhoneCodeExpiredError:
            return "ERROR", None, "รหัส OTP หมดอายุแล้ว กรุณาเริ่มใหม่อีกครั้ง"
    except asyncio.TimeoutError:
        return "ERROR", None, "การยืนยันรหัส OTP หมดเวลา (Timeout) กรุณาลองใหม่อีกครั้ง"
    except Exception as e:
        return "ERROR", None, str(e)
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def verify_2fa(user_id: int, password: str, api_id: int, api_hash: str):
    """
    Verify 2FA password.
    Returns: (success: bool, user_info: dict, error_msg: str)
    """
    api_id_int, api_hash_clean = validate_api_credentials(api_id, api_hash)

    session_path = get_user_session_path(user_id)
    client = TelegramClient(session_path, api_id_int, api_hash_clean)
    try:
        await asyncio.wait_for(client.connect(), timeout=8.0)
        await asyncio.wait_for(client.sign_in(password=password), timeout=10.0)
        me = await asyncio.wait_for(client.get_me(), timeout=6.0)
        username = f"@{me.username}" if me and me.username else (me.first_name if me else f"ID: {user_id}")
        return True, {"username": username, "id": me.id}, None
    except asyncio.TimeoutError:
        return False, None, "การยืนยัน 2FA หมดเวลา (Timeout) กรุณาลองใหม่อีกครั้ง"
    except Exception as e:
        return False, None, str(e)
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def logout_user(user_id: int, api_id: int, api_hash: str) -> bool:
    """Log out and remove user's session file."""
    api_id_int, api_hash_clean = validate_api_credentials(api_id, api_hash)

    session_path = get_user_session_path(user_id)
    session_file = get_session_file(user_id)
    if session_file.exists():
        client = TelegramClient(session_path, api_id_int, api_hash_clean)
        try:
            await asyncio.wait_for(client.connect(), timeout=5.0)
            if await client.is_user_authorized():
                await client.log_out()
        except Exception:
            pass
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

        try:
            if session_file.exists():
                os.remove(session_file)
        except Exception:
            pass
        return True
    return False
