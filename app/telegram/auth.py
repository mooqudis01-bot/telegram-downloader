"""
app/telegram/auth.py - Telethon StringSession Authentication & User Quota/VIP Service (MongoDB Atlas Permanent Persistence)
"""

import os
import json
import time
import asyncio
import tempfile
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError

try:
    from pymongo import MongoClient
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False

DEFAULT_API_ID = 32825705
DEFAULT_API_HASH = "4023849266ed4dfcd584031ce6b2a5f4"
DEFAULT_FREE_CREDITS = 2
ADMIN_IDS = [8314575937]
DEFAULT_MONGO_URI = "mongodb+srv://mooqudis01_db_user:MJKloerFOMOMqGby@cluster0.ypdls9r.mongodb.net/?retryWrites=true&w=majority"

mongo_client = None


def is_admin(user_id: int) -> bool:
    """Check if user_id is an authorized Admin."""
    admin_id_str = os.getenv("ADMIN_ID", "8314575937").strip()
    try:
        admin_ids = [int(x.strip()) for x in admin_id_str.split(",") if x.strip().isdigit()]
    except Exception:
        admin_ids = [8314575937]
    return user_id in admin_ids or user_id in ADMIN_IDS


def get_mongo_collection():
    """Returns MongoDB collection for user sessions if available."""
    global mongo_client
    if not MONGODB_AVAILABLE:
        return None
    mongo_uri = os.getenv("MONGODB_URI", DEFAULT_MONGO_URI).strip()
    if not mongo_uri:
        return None
    try:
        if mongo_client is None:
            mongo_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=4000)
        db = mongo_client["telegram_downloader"]
        return db["user_sessions"]
    except Exception:
        return None


def get_storage_file() -> Path:
    """Returns path to user_sessions.json as local fallback."""
    if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        d = Path(tempfile.gettempdir()) / "telegram_downloader_data"
        d.mkdir(exist_ok=True)
        return d / "user_sessions.json"

    try:
        d = Path("sessions")
        d.mkdir(exist_ok=True)
        return d / "user_sessions.json"
    except Exception:
        d = Path(tempfile.gettempdir()) / "telegram_downloader_data"
        d.mkdir(exist_ok=True)
        return d / "user_sessions.json"


def load_user_sessions() -> dict:
    """Load all saved user StringSessions and credits from MongoDB Atlas or local JSON file."""
    col = get_mongo_collection()
    if col is not None:
        try:
            sessions = {}
            for doc in col.find():
                uid = str(doc.get("user_id", ""))
                if uid:
                    doc_copy = dict(doc)
                    doc_copy.pop("_id", None)
                    sessions[uid] = doc_copy
            return sessions
        except Exception:
            pass

    filepath = get_storage_file()
    if filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def get_user_data(user_id: int) -> dict:
    """Get full user data dict including session, credits, and VIP status."""
    col = get_mongo_collection()
    if col is not None:
        try:
            doc = col.find_one({"user_id": str(user_id)})
            if doc:
                doc_copy = dict(doc)
                doc_copy.pop("_id", None)
                if "credits" not in doc_copy: doc_copy["credits"] = DEFAULT_FREE_CREDITS
                if "download_count" not in doc_copy: doc_copy["download_count"] = 0
                if "username" not in doc_copy: doc_copy["username"] = f"ID: {user_id}"
                if "vip_until" not in doc_copy: doc_copy["vip_until"] = 0
                return doc_copy
        except Exception:
            pass

    sessions = load_user_sessions()
    raw = sessions.get(str(user_id), {})
    if isinstance(raw, str):
        data = {"user_id": str(user_id), "session": raw, "username": f"ID: {user_id}", "credits": DEFAULT_FREE_CREDITS, "download_count": 0, "vip_until": 0}
    elif isinstance(raw, dict):
        data = raw
        data["user_id"] = str(user_id)
        if "credits" not in data: data["credits"] = DEFAULT_FREE_CREDITS
        if "download_count" not in data: data["download_count"] = 0
        if "username" not in data: data["username"] = f"ID: {user_id}"
        if "vip_until" not in data: data["vip_until"] = 0
    else:
        data = {"user_id": str(user_id), "session": "", "username": f"ID: {user_id}", "credits": DEFAULT_FREE_CREDITS, "download_count": 0, "vip_until": 0}
    return data


def save_user_data(user_id: int, data: dict):
    """Save user data dict to MongoDB Atlas and local fallback."""
    data["user_id"] = str(user_id)
    
    col = get_mongo_collection()
    if col is not None:
        try:
            col.update_one({"user_id": str(user_id)}, {"$set": data}, upsert=True)
        except Exception:
            pass

    filepath = get_storage_file()
    sessions = load_user_sessions()
    sessions[str(user_id)] = data
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(sessions, f, indent=2)
    except Exception:
        pass


def is_user_vip(user_id: int) -> bool:
    """Check if user currently has an active VIP Unlimited subscription."""
    data = get_user_data(user_id)
    vip_until = data.get("vip_until", 0)
    return vip_until > time.time()


def get_vip_remaining_days(user_id: int) -> int:
    """Returns remaining VIP days for user."""
    data = get_user_data(user_id)
    vip_until = data.get("vip_until", 0)
    now = time.time()
    if vip_until > now:
        remaining_seconds = vip_until - now
        return max(1, int(remaining_seconds / 86400))
    return 0


def add_user_vip_days(user_id: int, days: int) -> float:
    """Grant VIP Unlimited access for specified number of days."""
    data = get_user_data(user_id)
    now = time.time()
    current_until = data.get("vip_until", 0)
    if current_until > now:
        new_until = current_until + (days * 86400)
    else:
        new_until = now + (days * 86400)
    data["vip_until"] = new_until
    save_user_data(user_id, data)
    return new_until


def update_user_profile(user_id: int, username: str = "", first_name: str = ""):
    """Record user's Telegram username or display name."""
    data = get_user_data(user_id)
    if username:
        data["username"] = username if username.startswith("@") else f"@{username}"
    elif first_name:
        data["username"] = first_name
    save_user_data(user_id, data)


def get_all_users_list() -> list:
    """Get list of all registered users for Admin Dashboard."""
    sessions = load_user_sessions()
    result = []
    for user_id_str, data in sessions.items():
        try:
            uid = int(user_id_str)
        except ValueError:
            continue
        
        if isinstance(data, str):
            session_str = data
            username = f"ID: {uid}"
            credits = DEFAULT_FREE_CREDITS
            download_count = 0
            is_vip = False
            vip_days = 0
        elif isinstance(data, dict):
            session_str = data.get("session", "")
            username = data.get("username", "") or data.get("first_name", "") or f"ID: {uid}"
            credits = data.get("credits", DEFAULT_FREE_CREDITS)
            download_count = data.get("download_count", 0)
            vip_until = data.get("vip_until", 0)
            is_vip = vip_until > time.time()
            vip_days = max(1, int((vip_until - time.time()) / 86400)) if is_vip else 0
        else:
            continue

        result.append({
            "user_id": uid,
            "username": username,
            "connected": bool(session_str),
            "credits": credits,
            "download_count": download_count,
            "is_vip": is_vip,
            "vip_days": vip_days,
            "is_admin": is_admin(uid)
        })
    return result


def save_user_session(user_id: int, session_str: str):
    """Save user's StringSession to persistent storage."""
    data = get_user_data(user_id)
    data["session"] = session_str
    save_user_data(user_id, data)


def delete_user_session(user_id: int):
    """Remove user's StringSession."""
    data = get_user_data(user_id)
    data["session"] = ""
    save_user_data(user_id, data)


def get_user_session_string(user_id: int) -> str:
    """Get saved session string for user."""
    data = get_user_data(user_id)
    return data.get("session", "")


def get_user_credits(user_id: int) -> int:
    """Get user's remaining download credits."""
    data = get_user_data(user_id)
    return data.get("credits", DEFAULT_FREE_CREDITS)


def add_user_credits(user_id: int, amount: int) -> int:
    """Add download credits to user."""
    data = get_user_data(user_id)
    current = data.get("credits", DEFAULT_FREE_CREDITS)
    new_credits = current + amount
    data["credits"] = new_credits
    save_user_data(user_id, data)
    return new_credits


def deduct_user_credit(user_id: int) -> bool:
    """Deduct 1 download credit from user. VIP users are free & unlimited."""
    if is_user_vip(user_id):
        data = get_user_data(user_id)
        data["download_count"] = data.get("download_count", 0) + 1
        save_user_data(user_id, data)
        return True

    data = get_user_data(user_id)
    current = data.get("credits", DEFAULT_FREE_CREDITS)
    if current <= 0:
        return False
    data["credits"] = current - 1
    data["download_count"] = data.get("download_count", 0) + 1
    save_user_data(user_id, data)
    return True


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
    """Check if session string exists for user."""
    session_str = get_user_session_string(user_id)
    return bool(session_str)


async def check_user_session(user_id: int, api_id: int, api_hash: str) -> dict:
    data = get_user_data(user_id)
    credits = data.get("credits", DEFAULT_FREE_CREDITS)
    session_str = data.get("session", "")
    admin_flag = is_admin(user_id)
    saved_username = data.get("username", f"ID: {user_id}")
    vip_flag = is_user_vip(user_id)
    vip_days = get_vip_remaining_days(user_id)

    if not session_str:
        return {"connected": False, "credits": credits, "is_vip": vip_flag, "vip_days": vip_days, "username": saved_username, "is_admin": admin_flag}

    api_id_int, api_hash_clean = validate_api_credentials(api_id, api_hash)
    client = TelegramClient(StringSession(session_str), api_id_int, api_hash_clean)
    try:
        await asyncio.wait_for(client.connect(), timeout=6.0)
        if await asyncio.wait_for(client.is_user_authorized(), timeout=6.0):
            me = await asyncio.wait_for(client.get_me(), timeout=6.0)
            username = f"@{me.username}" if me and me.username else (me.first_name if me else f"ID: {user_id}")
            update_user_profile(user_id, username=me.username if me else "", first_name=me.first_name if me else "")
            return {
                "connected": True,
                "username": username,
                "id": me.id if me else user_id,
                "credits": credits,
                "is_vip": vip_flag,
                "vip_days": vip_days,
                "is_admin": admin_flag
            }
        else:
            delete_user_session(user_id)
            return {"connected": False, "credits": credits, "is_vip": vip_flag, "vip_days": vip_days, "username": saved_username, "is_admin": admin_flag}
    except Exception:
        return {"connected": True, "id": user_id, "username": saved_username, "credits": credits, "is_vip": vip_flag, "vip_days": vip_days, "is_admin": admin_flag}
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def send_otp(user_id: int, phone_number: str, api_id: int, api_hash: str):
    api_id_int, api_hash_clean = validate_api_credentials(api_id, api_hash)
    phone_clean = phone_number.strip().replace(" ", "").replace("-", "")

    client = TelegramClient(StringSession(), api_id_int, api_hash_clean)
    try:
        await asyncio.wait_for(client.connect(), timeout=8.0)
        res = await asyncio.wait_for(client.send_code_request(phone_clean), timeout=10.0)
        
        temp_session = client.session.save()
        save_user_session(user_id, temp_session)

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
    api_id_int, api_hash_clean = validate_api_credentials(api_id, api_hash)
    phone_clean = phone_number.strip().replace(" ", "").replace("-", "")
    session_str = get_user_session_string(user_id)

    client = TelegramClient(StringSession(session_str), api_id_int, api_hash_clean)
    try:
        await asyncio.wait_for(client.connect(), timeout=8.0)
        try:
            await asyncio.wait_for(client.sign_in(phone=phone_clean, code=code, phone_code_hash=phone_code_hash), timeout=10.0)
            
            final_session = client.session.save()
            save_user_session(user_id, final_session)

            me = await asyncio.wait_for(client.get_me(), timeout=6.0)
            username = f"@{me.username}" if me and me.username else (me.first_name if me else f"ID: {user_id}")
            update_user_profile(user_id, username=me.username if me else "", first_name=me.first_name if me else "")

            credits = get_user_credits(user_id)
            admin_flag = is_admin(user_id)
            return "SUCCESS", {"username": username, "id": me.id, "credits": credits, "is_admin": admin_flag}, None
        except SessionPasswordNeededError:
            temp_session = client.session.save()
            save_user_session(user_id, temp_session)
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
    api_id_int, api_hash_clean = validate_api_credentials(api_id, api_hash)
    session_str = get_user_session_string(user_id)

    client = TelegramClient(StringSession(session_str), api_id_int, api_hash_clean)
    try:
        await asyncio.wait_for(client.connect(), timeout=8.0)
        await asyncio.wait_for(client.sign_in(password=password), timeout=10.0)
        
        final_session = client.session.save()
        save_user_session(user_id, final_session)

        me = await asyncio.wait_for(client.get_me(), timeout=6.0)
        username = f"@{me.username}" if me and me.username else (me.first_name if me else f"ID: {user_id}")
        update_user_profile(user_id, username=me.username if me else "", first_name=me.first_name if me else "")

        credits = get_user_credits(user_id)
        admin_flag = is_admin(user_id)
        return True, {"username": username, "id": me.id, "credits": credits, "is_admin": admin_flag}, None
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
    session_str = get_user_session_string(user_id)
    if session_str:
        api_id_int, api_hash_clean = validate_api_credentials(api_id, api_hash)
        client = TelegramClient(StringSession(session_str), api_id_int, api_hash_clean)
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

        delete_user_session(user_id)
        return True
    return False
