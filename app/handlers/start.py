"""
app/handlers/start.py - Start Command, Admin Credit Management, TrueMoney Angpao (VIP Unlimited 300B/week)
"""

import os
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, FSInputFile
from aiogram.utils.markdown import html_decoration as hd

from app.telegram.auth import (
    check_user_session,
    get_user_credits,
    add_user_credits,
    is_admin,
    update_user_profile,
    is_user_vip,
    get_vip_remaining_days,
    add_user_vip_days
)
from app.telegram.media import download_media_from_link
from app.services.truemoney import redeem_truemoney_angpao

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
    user_id = message.from_user.id
    raw_user_name = message.from_user.full_name if message.from_user else "User"
    user_name = hd.quote(raw_user_name)
    
    tg_username = message.from_user.username if message.from_user else ""
    update_user_profile(user_id, username=tg_username, first_name=raw_user_name)

    api_id, api_hash = get_api_credentials()
    webapp_url = get_webapp_url()

    session_info = await check_user_session(user_id, api_id, api_hash)
    credits = get_user_credits(user_id)
    admin_flag = is_admin(user_id)
    vip_flag = is_user_vip(user_id)
    vip_days = get_vip_remaining_days(user_id)

    quota_badge = f"👑 <b>VIP Status:</b> Unlimited (เหลืออีก {vip_days} วัน)" if vip_flag else f"🎟️ <b>โควตาดาวน์โหลดคงเหลือ:</b> <code>{credits} ครั้ง</code>"

    if session_info.get("connected"):
        username = hd.quote(session_info.get("username", user_name))
        admin_badge = "\n👑 <b>Role:</b> System Admin\n" if admin_flag else ""
        text = (
            f"👋 <b>สวัสดีครับคุณ {user_name}!</b>\n\n"
            "🤖 <b>ยินดีต้อนรับสู่ Telegram Downloader MiniApp</b>\n\n"
            f"🟢 <b>Telegram Account:</b> Connected (<code>{username}</code>)\n"
            f"📱 <b>Telegram ID:</b> <code>{user_id}</code>"
            f"{admin_badge}\n"
            f"{quota_badge}\n\n"
            "✨ <b>แพ็กเกจเติมเงิน (TrueMoney ซองอั่งเปา):</b>\n"
            "• 🎟️ <b>50 บาท</b> = 10 ครั้งดาวน์โหลด\n"
            "• 👑 <b>300 บาท</b> = VIP ดาวน์โหลดไม่จำกัด 7 วัน (1 สัปดาห์)!\n\n"
            "ส่ง Telegram Link เพื่อดาวน์โหลดสื่อ หรือส่ง **ลิงก์ซองอั่งเปา TrueMoney** มาในแชทนี้เพื่อเติมเงินอัตโนมัติได้ทันที!"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 เปิด Telegram MiniApp", web_app=WebAppInfo(url=webapp_url))],
            [InlineKeyboardButton(text="🔓 Logout", callback_data="logout")]
        ])
    else:
        text = (
            f"👋 <b>สวัสดีครับคุณ {user_name}!</b>\n\n"
            "🤖 <b>ยินดีต้อนรับสู่ Telegram Downloader MiniApp</b>\n\n"
            "🔴 <b>Telegram Account:</b> Not Connected\n"
            f"{quota_badge} (ทดลองฟรี 2 ครั้ง)\n\n"
            "กรุณาเลือกช่องทางเข้าสู่ระบบด้านล่างเพื่อเริ่มใช้งานดาวน์โหลด Media:"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 เปิด Telegram MiniApp", web_app=WebAppInfo(url=webapp_url))],
            [InlineKeyboardButton(text="🔐 Login ผ่าน Telegram Chat", callback_data="login_start")]
        ])

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.message(Command("credits"))
async def check_credits_handler(message: Message):
    user_id = message.from_user.id
    credits = get_user_credits(user_id)
    vip_flag = is_user_vip(user_id)
    vip_days = get_vip_remaining_days(user_id)

    if vip_flag:
        status_text = f"👑 <b>สถานะบัญชี: VIP Unlimited (ดาวน์โหลดไม่จำกัด)</b>\n📅 <b>ระยะเวลา VIP คงเหลือ:</b> <code>{vip_days} วัน</code>"
    else:
        status_text = f"🎟️ <b>โควตาดาวน์โหลดคงเหลือของคุณ:</b> <code>{credits} ครั้ง</code>"

    await message.answer(
        f"{status_text}\n\n"
        "🧧 <b>แพ็กเกจเติมเงิน TrueMoney Wallet:</b>\n"
        "• 50 บาท = 10 ครั้งดาวน์โหลด\n"
        "• 👑 <b>300 บาท = VIP ไม่จำกัด 7 วัน (1 สัปดาห์)</b>\n\n"
        "สร้างซองอั่งเปา TrueMoney แล้วส่งลิงก์เข้ามาในแชทนี้เพื่อเปิดใช้งานอัตโนมัติได้ทันทีครับ!",
        parse_mode="HTML"
    )


@router.message(Command("addcredits"))
async def add_credits_handler(message: Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("⛔ <b>สิทธิ์การใช้งานปฏิเสธ:</b> เฉพาะแอดมินเท่านั้นที่สามารถเติมเครดิตได้", parse_mode="HTML")
        return

    parts = message.text.strip().split()
    if len(parts) < 3:
        await message.answer(
            "⚠️ <b>วิธีใช้งานคำสั่งเติมเครดิต/VIP (Admin):</b>\n\n"
            "• เติมครั้ง: <code>/addcredits <User_ID> <จำนวนครั้ง></code> (เช่น /addcredits 8314575937 50)\n"
            "• เติม VIP: <code>/addcredits <User_ID> vip <จำนวนวัน></code> (เช่น /addcredits 8314575937 vip 7)",
            parse_mode="HTML"
        )
        return

    target_user_id = int(parts[1])
    arg2 = parts[2].lower()

    if arg2 == "vip":
        days = int(parts[3]) if len(parts) >= 4 else 7
        add_user_vip_days(target_user_id, days)
        await message.answer(
            f"👑 <b>เติมสิทธิ์ VIP ไม่จำกัด สำเร็จ!</b>\n\n"
            f"👤 <b>Telegram ID:</b> <code>{target_user_id}</code>\n"
            f"📅 <b>เพิ่มระยะเวลา VIP:</b> <code>+{days} วัน</code>",
            parse_mode="HTML"
        )
    else:
        amount = int(arg2)
        new_balance = add_user_credits(target_user_id, amount)
        await message.answer(
            f"✅ <b>เติมเครดิตสำเร็จ!</b>\n\n"
            f"👤 <b>Telegram ID:</b> <code>{target_user_id}</code>\n"
            f"➕ <b>จำนวนที่เติม:</b> <code>+{amount} ครั้ง</code>\n"
            f"🎟️ <b>ยอดคงเหลือใหม่:</b> <code>{new_balance} ครั้ง</code>",
            parse_mode="HTML"
        )


@router.message(F.text.contains("gift.truemoney.com"))
async def truemoney_angpao_handler(message: Message):
    user_id = message.from_user.id
    link = message.text.strip()
    phone = os.getenv("TRUEMONEY_PHONE", "0834274788").strip()

    status_msg = await message.answer("🔄 <b>กำลังตรวจสอบและรับซองอั่งเปา TrueMoney Wallet...</b>", parse_mode="HTML")

    success, amount, error_msg = await redeem_truemoney_angpao(phone, link)

    if success:
        if amount >= 300:
            vip_weeks = int(amount / 300.0)
            vip_days = vip_weeks * 7
            add_user_vip_days(user_id, vip_days)
            rem_days = get_vip_remaining_days(user_id)
            await status_msg.edit_text(
                f"🎉 <b>ปลดล็อค VIP Unlimited สำเร็จเรียบร้อยแล้ว!</b>\n\n"
                f"🧧 <b>ยอดซองอั่งเปา:</b> <code>{amount:.2f} บาท</code>\n"
                f"👑 <b>ได้รับสิทธิ์ VIP ดาวน์โหลดไม่จำกัด:</b> <code>+{vip_days} วัน</code> (300 บาท/สัปดาห์)\n"
                f"📅 <b>ระยะเวลา VIP รวมคงเหลือ:</b> <code>{rem_days} วัน</code>\n\n"
                "เพลิดเพลินกับการดาวน์โหลดได้ไม่จำกัดครับ ✨",
                parse_mode="HTML"
            )
        else:
            credits_to_add = int(amount / 5.0)
            if credits_to_add <= 0:
                credits_to_add = 1

            new_balance = add_user_credits(user_id, credits_to_add)
            await status_msg.edit_text(
                f"🎉 <b>เติมเงินสำเร็จเรียบร้อยแล้ว!</b>\n\n"
                f"🧧 <b>ยอดซองอั่งเปา:</b> <code>{amount:.2f} บาท</code>\n"
                f"➕ <b>โควตาที่ได้รับ:</b> <code>+{credits_to_add} ครั้ง</code> (อัตรา 50 บาท = 10 ครั้ง)\n"
                f"🎟️ <b>ยอดโควตาคงเหลือใหม่:</b> <code>{new_balance} ครั้ง</code>\n\n"
                "ขอบคุณที่ใช้บริการครับ ✨",
                parse_mode="HTML"
            )
    else:
        await status_msg.edit_text(f"❌ <b>เติมซองอั่งเปาไม่สำเร็จ:</b> {error_msg}", parse_mode="HTML")


@router.message(F.text.contains("t.me/"))
async def link_download_handler(message: Message):
    user_id = message.from_user.id
    link = message.text.strip()
    api_id, api_hash = get_api_credentials()

    tg_username = message.from_user.username if message.from_user else ""
    raw_user_name = message.from_user.full_name if message.from_user else ""
    update_user_profile(user_id, username=tg_username, first_name=raw_user_name)

    credits = get_user_credits(user_id)
    vip_flag = is_user_vip(user_id)

    if not vip_flag and credits <= 0:
        await message.answer(
            "❌ <b>โควตาดาวน์โหลดของคุณหมดแล้ว! (0 ครั้ง)</b>\n\n"
            "🧧 <b>สมัครเพิ่มได้ในแชทนี้:</b>\n"
            "• เติมตามครั้ง: 50 บาท = 10 ครั้ง\n"
            "• 👑 <b>VIP Unlimited: 300 บาท = ดาวน์โหลดไม่จำกัด 7 วัน</b>",
            parse_mode="HTML"
        )
        return

    status_msg = await message.answer("🔄 <b>กำลังดึงข้อมูลและดาวน์โหลด Media จาก Telegram...</b>", parse_mode="HTML")

    success, file_path, filename, error_msg = await download_media_from_link(user_id, link, api_id, api_hash)

    if success and file_path and os.path.exists(file_path):
        rem_vip = get_vip_remaining_days(user_id)
        quota_text = f"👑 VIP Unlimited (เหลืออีก {rem_vip} วัน)" if vip_flag else f"🎟️ โควตาคงเหลือ: {get_user_credits(user_id)} ครั้ง"
        
        await status_msg.edit_text(f"📤 <b>ดาวน์โหลดสำเร็จ! กำลังส่งไฟล์ {hd.quote(filename)} ...</b>", parse_mode="HTML")
        try:
            input_file = FSInputFile(file_path)
            await message.answer_document(
                document=input_file,
                caption=f"✅ <b>{hd.quote(filename)}</b>\n📥 จากลิงก์: {hd.quote(link)}\n{quota_text}",
                parse_mode="HTML"
            )
            await status_msg.delete()
        except Exception:
            await status_msg.edit_text(
                f"✅ <b>ดาวน์โหลดสำเร็จเรียบร้อยแล้ว!</b>\n📁 ไฟล์: <code>{hd.quote(filename)}</code>\n{quota_text}",
                parse_mode="HTML"
            )
    else:
        err = hd.quote(error_msg or "เกิดข้อผิดพลาดในการดาวน์โหลด")
        await status_msg.edit_text(f"❌ <b>ดาวน์โหลดไม่สำเร็จ:</b> {err}", parse_mode="HTML")
