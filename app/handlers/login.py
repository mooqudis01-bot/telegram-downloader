"""
app/handlers/login.py - Login & Authentication Handlers using Telethon + aiogram 3.x with HTML formatting
"""

import os
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.markdown import html_decoration as hd

from app.telegram.auth import send_otp, verify_otp, verify_2fa, logout_user

router = Router()


class LoginStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_otp = State()
    waiting_for_2fa = State()


def get_api_credentials():
    api_id_str = os.getenv("API_ID", "").strip()
    api_hash = os.getenv("API_HASH", "").strip()
    try:
        api_id = int(api_id_str)
    except ValueError:
        api_id = 0
    return api_id, api_hash


def get_webapp_url():
    return os.getenv("WEBAPP_URL", "http://localhost:8000/miniapp").strip()


def get_connected_keyboard():
    webapp_url = get_webapp_url()
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 เปิด Telegram MiniApp", web_app=WebAppInfo(url=webapp_url))],
        [InlineKeyboardButton(text="🔗 วิธีส่ง Telegram Link", callback_data="send_link_info")],
        [InlineKeyboardButton(text="🔓 Logout", callback_data="logout")]
    ])


def get_login_keyboard():
    webapp_url = get_webapp_url()
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 เปิด Telegram MiniApp", web_app=WebAppInfo(url=webapp_url))],
        [InlineKeyboardButton(text="🔐 Login ผ่าน Telegram Chat", callback_data="login_start")]
    ])


@router.callback_query(F.data == "login_start")
async def start_login_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(LoginStates.waiting_for_phone)
    await callback.message.edit_text(
        "📱 <b>กรุณาส่งเบอร์โทรศัพท์สำหรับ Telegram Account ของคุณ</b>\n\n"
        "ตัวอย่าง: <code>+66812345678</code> หรือ <code>+1234567890</code>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(LoginStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    phone = message.text.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+") or not phone[1:].isdigit():
        await message.answer(
            "❌ รูปแบบเบอร์โทรศัพท์ไม่ถูกต้อง!\n"
            "กรุณาระบุเครื่องหมาย <code>+</code> ตามด้วยรหัสประเทศ เช่น <code>+66812345678</code>",
            parse_mode="HTML"
        )
        return

    api_id, api_hash = get_api_credentials()
    if not api_id or not api_hash:
        await message.answer("❌ ไม่พบ API_ID หรือ API_HASH ในไฟล์ .env กรุณาตรวจสอบคอนฟิก", parse_mode="HTML")
        await state.clear()
        return

    user_id = message.from_user.id
    status_msg = await message.answer("🔄 กำลังส่งรหัส OTP ไปยัง Telegram ของคุณ...")

    success, phone_code_hash, error_msg = await send_otp(user_id, phone, api_id, api_hash)
    if success:
        await state.update_data(phone=phone, phone_code_hash=phone_code_hash)
        await state.set_state(LoginStates.waiting_for_otp)
        await status_msg.edit_text(
            "📲 <b>ระบบได้ส่งรหัส OTP ไปยัง Telegram ของคุณเรียบร้อยแล้ว</b>\n\n"
            "กรุณากรอกรหัส OTP (เช่น <code>12345</code>):",
            parse_mode="HTML"
        )
    else:
        err_text = hd.quote(error_msg or "Unknown error")
        await status_msg.edit_text(
            f"❌ ไม่สามารถส่ง OTP ได้: {err_text}\n\n"
            "กรุณากดปุ่มเพื่อลองใหม่อีกครั้ง",
            parse_mode="HTML",
            reply_markup=get_login_keyboard()
        )
        await state.clear()


@router.message(LoginStates.waiting_for_otp)
async def process_otp(message: Message, state: FSMContext):
    code = message.text.strip().replace(" ", "")
    data = await state.get_data()
    phone = data.get("phone")
    phone_code_hash = data.get("phone_code_hash")

    if not phone or not phone_code_hash:
        await message.answer("❌ เกิดข้อผิดพลาด กรุณาเริ่มกระบวนการ Login ใหม่อีกครั้ง", reply_markup=get_login_keyboard(), parse_mode="HTML")
        await state.clear()
        return

    api_id, api_hash = get_api_credentials()
    user_id = message.from_user.id
    status_msg = await message.answer("🔄 กำลังตรวจสอบรหัส OTP...")

    status, user_info, error_msg = await verify_otp(user_id, phone, phone_code_hash, code, api_id, api_hash)

    if status == "SUCCESS":
        await state.clear()
        username = hd.quote(user_info.get("username", "User"))
        user_tg_id = user_info.get("id", user_id)
        await status_msg.edit_text(
            "✅ <b>Login สำเร็จ!</b>\n\n"
            f"👤 <b>Account:</b> {username}\n"
            f"📱 <b>Telegram ID:</b> <code>{user_tg_id}</code>\n\n"
            "ตอนนี้คุณสามารถเปิด MiniApp หรือส่ง Telegram Message Link เพื่อดาวน์โหลด Media ได้ทันที",
            parse_mode="HTML",
            reply_markup=get_connected_keyboard()
        )
    elif status == "NEED_2FA":
        await state.set_state(LoginStates.waiting_for_2fa)
        await status_msg.edit_text(
            "🔐 <b>บัญชีของคุณมีการเปิด Two-Step Verification</b>\n\n"
            "กรุณากรอกรหัสผ่าน 2FA Password ของคุณ:",
            parse_mode="HTML"
        )
    elif status == "INVALID_CODE":
        await status_msg.edit_text(
            "❌ รหัส OTP ไม่ถูกต้อง! กรุณากรอกรหัส OTP ใหม่อีกครั้ง:",
            parse_mode="HTML"
        )
    else:
        err_text = hd.quote(error_msg or "Unknown error")
        await status_msg.edit_text(
            f"❌ เกิดข้อผิดพลาด: {err_text}\nกรุณาลองเข้าสู่ระบบใหม่อีกครั้ง",
            parse_mode="HTML",
            reply_markup=get_login_keyboard()
        )
        await state.clear()


@router.message(LoginStates.waiting_for_2fa)
async def process_2fa(message: Message, state: FSMContext):
    password = message.text.strip()
    api_id, api_hash = get_api_credentials()
    user_id = message.from_user.id
    status_msg = await message.answer("🔄 กำลังตรวจสอบรหัสผ่าน 2FA...")

    success, user_info, error_msg = await verify_2fa(user_id, password, api_id, api_hash)

    if success:
        await state.clear()
        username = hd.quote(user_info.get("username", "User"))
        user_tg_id = user_info.get("id", user_id)
        await status_msg.edit_text(
            "✅ <b>Login สำเร็จ!</b>\n\n"
            f"👤 <b>Account:</b> {username}\n"
            f"📱 <b>Telegram ID:</b> <code>{user_tg_id}</code>\n\n"
            "ตอนนี้คุณสามารถเปิด MiniApp หรือส่ง Telegram Message Link เพื่อดาวน์โหลด Media ได้ทันที",
            parse_mode="HTML",
            reply_markup=get_connected_keyboard()
        )
    else:
        err_text = hd.quote(error_msg or "Invalid 2FA Password")
        await status_msg.edit_text(
            f"❌ รหัสผ่าน 2FA ไม่ถูกต้อง หรือเกิดข้อผิดพลาด: {err_text}\n\n"
            "กรุณากรอกรหัสผ่าน 2FA ใหม่อีกครั้ง หรือกดปุ่มด้านล่างเพื่อเริ่มใหม่",
            parse_mode="HTML",
            reply_markup=get_login_keyboard()
        )


@router.callback_query(F.data == "logout")
async def logout_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    api_id, api_hash = get_api_credentials()
    user_id = callback.from_user.id

    await logout_user(user_id, api_id, api_hash)

    await callback.message.edit_text(
        "🔓 <b>ออกจากระบบเรียบร้อยแล้ว!</b>\n\n"
        "Session ของคุณถูกลบออกจากระบบแล้ว หากต้องการใช้งานใหม่กรุณากด Login หรือเปิด MiniApp",
        parse_mode="HTML",
        reply_markup=get_login_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "send_link_info")
async def send_link_info_callback(callback: CallbackQuery):
    await callback.message.reply(
        "📥 <b>วิธีส่ง Telegram Message Link:</b>\n\n"
        "คัดลอกลิงก์ข้อความ Telegram (เช่น <code>https://t.me/c/123456789/100</code> หรือ <code>https://t.me/channel/100</code>)\n"
        "แล้วส่งมาในแชทนี้ได้เลยครับ!",
        parse_mode="HTML"
    )
    await callback.answer()
