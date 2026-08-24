"""
app/web/server.py - Telegram MiniApp & FastAPI Web Application (iOS Safari Native Download Fix)
"""

import os
import tempfile
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Update, MenuButtonWebApp, WebAppInfo

from app.telegram.auth import (
    check_user_session,
    send_otp,
    verify_otp,
    verify_2fa,
    logout_user,
    get_user_credits,
    add_user_credits,
    is_admin,
    get_all_users_list,
    update_user_profile,
    is_user_vip,
    get_vip_remaining_days,
    add_user_vip_days
)
from app.telegram.media import download_media_from_link
from app.services.truemoney import redeem_truemoney_angpao
from app.handlers import start_router, login_router

app = FastAPI(
    title="Telegram Downloader MiniApp",
    description="Telegram MiniApp Interface & API for Telegram Downloader",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_API_ID = 32825705
DEFAULT_API_HASH = "4023849266ed4dfcd584031ce6b2a5f4"

# Global Aiogram Bot & Dispatcher for Webhook
bot_token = os.getenv("BOT_TOKEN", "8890827538:AAFVZqr1uIzYZIsscQ4ie2pS3uLcXrbEUdU").strip()
bot_instance = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp_instance = Dispatcher()
dp_instance.include_router(start_router)
dp_instance.include_router(login_router)


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


class SendOtpRequest(BaseModel):
    user_id: int
    phone: str


class VerifyOtpRequest(BaseModel):
    user_id: int
    phone: str
    phone_code_hash: str
    code: str


class Verify2faRequest(BaseModel):
    user_id: int
    password: str


class LogoutRequest(BaseModel):
    user_id: int


class DownloadRequest(BaseModel):
    user_id: int
    link: str


class AdminAddCreditsRequest(BaseModel):
    admin_id: int
    target_user_id: int
    amount: int
    is_vip: bool = False


class TrueMoneyTopupRequest(BaseModel):
    user_id: int
    link: str


@app.post("/api/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot_instance})
        await dp_instance.feed_webhook_update(bot_instance, update)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/api/set-webhook")
async def setup_webhook():
    webapp_url = os.getenv("WEBAPP_URL", "https://telegram-downloader-nggk.vercel.app/miniapp").strip()
    base_url = webapp_url.replace("/miniapp", "").rstrip("/")
    webhook_url = f"{base_url}/api/webhook"
    
    try:
        await bot_instance.delete_webhook(drop_pending_updates=True)
        await bot_instance.set_webhook(url=webhook_url)
        await bot_instance.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="📱 เปิด MiniApp", web_app=WebAppInfo(url=webapp_url))
        )
        return {"success": True, "webhook_url": webhook_url, "miniapp_url": webapp_url}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/topup/truemoney")
async def api_topup_truemoney(req: TrueMoneyTopupRequest):
    phone = os.getenv("TRUEMONEY_PHONE", "0834274788").strip()
    success, amount, error_msg = await redeem_truemoney_angpao(phone, req.link)

    if success:
        if amount >= 300:
            vip_weeks = int(amount / 300.0)
            vip_days = vip_weeks * 7
            add_user_vip_days(req.user_id, vip_days)
            rem_days = get_vip_remaining_days(req.user_id)
            return {
                "success": True,
                "message": f"👑 ปลดล็อค VIP Unlimited สำเร็จ! ได้รับสิทธิ์ดาวน์โหลดไม่จำกัด +{vip_days} วัน (ยอดซอง {amount:.2f} บาท)",
                "amount_baht": amount,
                "is_vip": True,
                "vip_days_remaining": rem_days
            }
        else:
            credits_to_add = int(amount / 5.0)
            if credits_to_add <= 0:
                credits_to_add = 1

            new_balance = add_user_credits(req.user_id, credits_to_add)
            return {
                "success": True,
                "message": f"เติมเงินสำเร็จ! ได้รับโควตา +{credits_to_add} ครั้ง (อัตรา 50 บาท = 10 ครั้ง)",
                "amount_baht": amount,
                "credits_added": credits_to_add,
                "new_balance": new_balance
            }
    else:
        raise HTTPException(status_code=400, detail=error_msg or "เติมซองอั่งเปาไม่สำเร็จ")


@app.get("/api/admin/users")
async def admin_get_users(admin_id: int):
    if not is_admin(admin_id):
        raise HTTPException(status_code=403, detail="⛔ สิทธิ์การใช้งานปฏิเสธ: เฉพาะแอดมินเท่านั้น")
    users = get_all_users_list()
    return {"success": True, "users": users}


@app.post("/api/admin/add-credits")
async def admin_add_credits(req: AdminAddCreditsRequest):
    if not is_admin(req.admin_id):
        raise HTTPException(status_code=403, detail="⛔ สิทธิ์การใช้งานปฏิเสธ: เฉพาะแอดมินเท่านั้น")
    
    if req.is_vip:
        days_to_add = req.amount if req.amount > 0 else 7
        add_user_vip_days(req.target_user_id, days_to_add)
        rem_days = get_vip_remaining_days(req.target_user_id)
        return {
            "success": True,
            "message": f"เติมสิทธิ์ VIP Unlimited ให้ User {req.target_user_id} จำนวน +{days_to_add} วันเรียบร้อย (คงเหลือ {rem_days} วัน)",
            "target_user_id": req.target_user_id,
            "is_vip": True,
            "vip_days": rem_days
        }
    else:
        new_credits = add_user_credits(req.target_user_id, req.amount)
        return {
            "success": True,
            "message": f"เติมเครดิตให้ User {req.target_user_id} จำนวน +{req.amount} ครั้งเรียบร้อย",
            "target_user_id": req.target_user_id,
            "new_credits": new_credits
        }


@app.get("/api/auth/status/{user_id}")
async def auth_status(user_id: int):
    api_id, api_hash = get_api_credentials()
    res = await check_user_session(user_id, api_id, api_hash)
    res["credits"] = get_user_credits(user_id)
    res["is_vip"] = is_user_vip(user_id)
    res["vip_days"] = get_vip_remaining_days(user_id)
    res["is_admin"] = is_admin(user_id)
    return res


@app.post("/api/auth/send-otp")
async def api_send_otp(req: SendOtpRequest):
    try:
        api_id, api_hash = get_api_credentials()
        success, phone_code_hash, error_msg = await send_otp(req.user_id, req.phone, api_id, api_hash)
        if success:
            return JSONResponse(content={"success": True, "phone_code_hash": phone_code_hash})
        else:
            return JSONResponse(status_code=400, content={"success": False, "detail": error_msg or "Failed to send OTP"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "detail": f"Server Error: {str(e)}"})


@app.post("/api/auth/verify-otp")
async def api_verify_otp(req: VerifyOtpRequest):
    try:
        api_id, api_hash = get_api_credentials()
        status, user_info, error_msg = await verify_otp(
            req.user_id, req.phone, req.phone_code_hash, req.code, api_id, api_hash
        )

        if status == "SUCCESS":
            return JSONResponse(content={"success": True, "need_2fa": False, "user": user_info})
        elif status == "NEED_2FA":
            return JSONResponse(content={"success": True, "need_2fa": True})
        else:
            return JSONResponse(status_code=400, content={"success": False, "detail": error_msg or "Verify OTP failed"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "detail": f"Server Error: {str(e)}"})


@app.post("/api/auth/verify-2fa")
async def api_verify_2fa(req: Verify2faRequest):
    try:
        api_id, api_hash = get_api_credentials()
        success, user_info, error_msg = await verify_2fa(req.user_id, req.password, api_id, api_hash)
        if success:
            return JSONResponse(content={"success": True, "user": user_info})
        else:
            return JSONResponse(status_code=400, content={"success": False, "detail": error_msg or "Invalid 2FA password"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "detail": f"Server Error: {str(e)}"})


@app.post("/api/auth/logout")
async def api_logout(req: LogoutRequest):
    api_id, api_hash = get_api_credentials()
    await logout_user(req.user_id, api_id, api_hash)
    return {"success": True, "message": "Logged out successfully"}


@app.post("/api/download")
async def create_download(req: DownloadRequest):
    if not req.link:
        raise HTTPException(status_code=400, detail="กรุณาระบุลิงก์ข้อความ Telegram")

    api_id, api_hash = get_api_credentials()
    success, file_path, filename, error_msg = await download_media_from_link(req.user_id, req.link, api_id, api_hash)

    if success:
        remaining = get_user_credits(req.user_id)
        vip_flag = is_user_vip(req.user_id)
        vip_days = get_vip_remaining_days(req.user_id)
        return {
            "success": True,
            "message": f"ดาวน์โหลดสำเร็จ! ไฟล์: {filename}",
            "filename": filename,
            "link": req.link,
            "credits_remaining": remaining,
            "is_vip": vip_flag,
            "vip_days_remaining": vip_days,
            "status": "completed"
        }
    else:
        raise HTTPException(status_code=400, detail=error_msg or "ดาวน์โหลดไม่สำเร็จ")


@app.get("/api/downloads/{filename}")
async def get_downloaded_file(filename: str):
    downloads_dir = get_downloads_dir()
    file_path = downloads_dir / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    
    # iOS Safari Direct Download Attachment Header (Forces iOS Safari to show 'Download' prompt instead of streaming player!)
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


MINIAPP_HTML = """<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Telegram Downloader</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        :root {
            --tg-bg: #0e1621;
            --tg-card: #17212b;
            --tg-input: #242f3d;
            --tg-blue: #3390ec;
            --tg-blue-hover: #2b82d9;
            --tg-text: #ffffff;
            --tg-subtext: #7f91a4;
            --tg-border: rgba(255, 255, 255, 0.08);
            --tg-green: #40b76e;
            --tg-red: #e53935;
            --tg-gold: #f59e0b;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; -webkit-tap-highlight-color: transparent; }

        body {
            background-color: var(--tg-bg);
            color: var(--tg-text);
            min-height: 100vh;
            padding: 16px 14px 32px 14px;
            display: flex;
            flex-direction: column;
        }

        .container {
            max-width: 440px;
            margin: 0 auto;
            width: 100%;
        }

        /* Profile Header Bar (Hidden by default until logged in) */
        .profile-card {
            background: var(--tg-card);
            border: 1px solid var(--tg-border);
            border-radius: 16px;
            padding: 14px 16px;
            margin-bottom: 14px;
            display: none;
            align-items: center;
            justify-content: space-between;
        }

        .profile-left {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .avatar {
            width: 42px;
            height: 42px;
            border-radius: 50%;
            background: var(--tg-blue);
            color: white;
            font-weight: 700;
            font-size: 15px;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .user-name {
            font-size: 15px;
            font-weight: 600;
            color: var(--tg-text);
        }

        .user-id {
            font-size: 12px;
            color: var(--tg-subtext);
            margin-top: 2px;
        }

        .credit-badge {
            background: rgba(51, 144, 236, 0.12);
            color: var(--tg-blue);
            border: 1px solid rgba(51, 144, 236, 0.25);
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }

        .vip-badge {
            background: rgba(245, 158, 11, 0.15) !important;
            color: var(--tg-gold) !important;
            border: 1px solid rgba(245, 158, 11, 0.3) !important;
        }

        /* Segmented Nav Bar */
        .nav-segmented {
            background: var(--tg-card);
            border: 1px solid var(--tg-border);
            border-radius: 12px;
            padding: 3px;
            display: none;
            margin-bottom: 16px;
        }

        .nav-btn {
            flex: 1;
            padding: 9px 2px;
            border: none;
            background: transparent;
            color: var(--tg-subtext);
            font-size: 12px;
            font-weight: 600;
            border-radius: 9px;
            cursor: pointer;
            transition: all 0.2s ease;
            text-align: center;
        }

        .nav-btn.active {
            background: var(--tg-blue);
            color: white;
        }

        /* Main Section Card */
        .section-card {
            background: var(--tg-card);
            border: 1px solid var(--tg-border);
            border-radius: 18px;
            padding: 24px 20px;
            margin-bottom: 16px;
            position: relative;
        }

        /* Mobile Banking Onboarding UI Flow */
        .app-hero-icon {
            width: 56px;
            height: 56px;
            background: rgba(51, 144, 236, 0.12);
            border: 1px solid rgba(51, 144, 236, 0.3);
            border-radius: 18px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 26px;
            margin: 0 auto 16px auto;
        }

        .step-title {
            font-size: 19px;
            font-weight: 700;
            color: var(--tg-text);
            text-align: center;
            margin-bottom: 6px;
        }

        .step-desc {
            font-size: 13px;
            color: var(--tg-subtext);
            text-align: center;
            margin-bottom: 22px;
            line-height: 1.5;
        }

        .form-group {
            margin-bottom: 18px;
        }

        .form-label {
            display: block;
            font-size: 12px;
            font-weight: 600;
            color: var(--tg-subtext);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        input[type="text"], input[type="password"], input[type="number"] {
            width: 100%;
            padding: 14px 16px;
            background: var(--tg-input);
            border: 1.5px solid var(--tg-border);
            border-radius: 12px;
            color: white;
            font-size: 15px;
            font-weight: 500;
            outline: none;
            transition: border-color 0.2s ease;
        }

        input:focus {
            border-color: var(--tg-blue);
        }

        /* Banking 5-Digit OTP Segmented Boxes */
        .otp-container {
            display: flex;
            justify-content: center;
            gap: 10px;
            margin: 20px 0;
        }

        .otp-box {
            width: 48px !important;
            height: 56px;
            font-size: 24px !important;
            font-weight: 800 !important;
            text-align: center;
            border-radius: 14px !important;
            border: 1.5px solid var(--tg-border) !important;
            background: var(--tg-input) !important;
            color: var(--tg-blue) !important;
            padding: 0 !important;
        }

        .otp-box:focus {
            border-color: var(--tg-blue) !important;
            box-shadow: 0 0 12px rgba(51, 144, 236, 0.3);
        }

        /* Pricing Card Grid */
        .price-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-bottom: 18px;
        }

        .price-card {
            background: var(--tg-input);
            border: 1px solid var(--tg-border);
            border-radius: 12px;
            padding: 12px;
            text-align: center;
        }

        .price-card.vip {
            border-color: rgba(245, 158, 11, 0.4);
            background: rgba(245, 158, 11, 0.06);
        }

        .price-title { font-size: 13px; font-weight: 700; color: white; margin-bottom: 4px; }
        .price-val { font-size: 16px; font-weight: 800; color: var(--tg-blue); }
        .price-card.vip .price-val { color: var(--tg-gold); }

        /* Buttons */
        .btn-primary {
            width: 100%;
            padding: 14px;
            background: var(--tg-blue);
            border: none;
            border-radius: 12px;
            color: white;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s ease, transform 0.1s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            text-decoration: none;
        }

        .btn-primary:hover {
            background: var(--tg-blue-hover);
        }

        .btn-primary:active {
            transform: scale(0.98);
        }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.06);
            color: var(--tg-subtext);
            margin-top: 10px;
            border: 1px solid var(--tg-border);
        }

        .btn-danger {
            background: rgba(229, 57, 53, 0.15);
            color: #ef5350;
            margin-top: 10px;
        }

        .btn-save-ios {
            background: #40b76e !important;
            margin-top: 14px;
            font-weight: 700;
        }

        .btn-sm {
            padding: 6px 12px;
            font-size: 12px;
            border-radius: 8px;
            width: auto;
        }

        /* Info & Alert */
        .info-box {
            background: rgba(51, 144, 236, 0.08);
            border: 1px solid rgba(51, 144, 236, 0.2);
            border-radius: 12px;
            padding: 14px;
            margin-bottom: 18px;
            font-size: 12px;
            color: #b0c4de;
            line-height: 1.6;
        }

        .alert-bar {
            padding: 12px 14px;
            border-radius: 12px;
            font-size: 13px;
            font-weight: 500;
            margin-bottom: 14px;
            display: none;
        }

        .alert-error {
            background: rgba(229, 57, 53, 0.15);
            border: 1px solid rgba(229, 57, 53, 0.3);
            color: #ef5350;
        }

        .alert-success {
            background: rgba(64, 183, 110, 0.15);
            border: 1px solid rgba(64, 183, 110, 0.3);
            color: #81c784;
        }

        /* Item Row */
        .item-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: var(--tg-input);
            border: 1px solid var(--tg-border);
            border-radius: 12px;
            padding: 12px 14px;
            margin-bottom: 8px;
        }

        .item-name {
            font-size: 13px;
            font-weight: 600;
            color: var(--tg-text);
        }

        .item-sub {
            font-size: 11px;
            color: var(--tg-subtext);
            margin-top: 2px;
        }

        .tab-content { display: none; }
        .tab-content.active { display: block; }
        
        .step-box { display: none; }
        .step-box.active { display: block; animation: fadeIn 0.25s ease; }

        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

        .spinner {
            width: 16px; height: 16px;
            border: 2px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 0.6s linear infinite;
            display: none;
        }

        @keyframes spin { to { transform: rotate(360deg); } }

        /* Download Progress Modal Popup Overlay */
        .modal-overlay {
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.82);
            backdrop-filter: blur(8px);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 9999;
            padding: 20px;
            animation: fadeIn 0.25s ease;
        }

        .modal-card {
            background: var(--tg-card);
            border: 1px solid var(--tg-border);
            border-radius: 22px;
            padding: 26px 22px;
            width: 100%;
            max-width: 380px;
            text-align: center;
            box-shadow: 0 20px 50px rgba(0,0,0,0.6);
        }

        .modal-icon {
            font-size: 38px;
            margin-bottom: 10px;
        }

        .modal-title {
            font-size: 17px;
            font-weight: 700;
            color: white;
            margin-bottom: 4px;
        }

        .modal-subtitle {
            font-size: 12px;
            color: var(--tg-subtext);
            margin-bottom: 20px;
            word-break: break-all;
        }

        .progress-track {
            background: var(--tg-input);
            border-radius: 10px;
            height: 12px;
            overflow: hidden;
            margin: 16px 0 10px 0;
            border: 1px solid var(--tg-border);
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #3390ec, #40b76e);
            width: 0%;
            transition: width 0.2s ease;
            border-radius: 10px;
        }

        .progress-stats {
            display: flex;
            justify-content: space-between;
            font-size: 13px;
            margin-bottom: 14px;
        }

        .eta-box {
            background: var(--tg-input);
            border-radius: 12px;
            padding: 12px 14px;
            font-size: 12px;
            display: flex;
            justify-content: space-between;
            color: var(--tg-subtext);
            border: 1px solid var(--tg-border);
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Profile Header Bar (Hidden by default until logged in) -->
        <div class="profile-card" id="header-bar-card">
            <div class="profile-left">
                <div class="avatar" id="hdr-avatar">TG</div>
                <div>
                    <div class="user-name" id="hdr-name">Telegram Account</div>
                    <div class="user-id" id="hdr-id">ID: 000000</div>
                </div>
            </div>
            <div class="credit-badge" id="hdr-credits">
                🎟️ <span>2 ครั้ง</span>
            </div>
        </div>

        <!-- Segmented Control Nav Bar (No Files tab) -->
        <div class="nav-segmented" id="main-nav-bar">
            <button class="nav-btn active" onclick="switchTab('auth', event)">Account</button>
            <button class="nav-btn" onclick="switchTab('download', event)">Downloader</button>
            <button class="nav-btn" onclick="switchTab('topup', event)">เติมเงิน/VIP</button>
            <button class="nav-btn" id="admin-tab-btn" style="display: none;" onclick="switchTab('admin', event)">Admin</button>
        </div>

        <div id="alert-box" class="alert-bar"></div>

        <!-- TAB 1: ACCOUNT (MOBILE BANKING ONBOARDING FLOW) -->
        <div id="tab-auth" class="tab-content active">
            <div class="section-card">
                <!-- Step 1: Mobile Phone Entry -->
                <div id="auth-step-1" class="step-box active">
                    <div class="app-hero-icon">📱</div>
                    <h2 class="step-title">เข้าสู่ระบบ Telegram Account</h2>
                    <p class="step-desc">กรอกเบอร์โทรศัพท์ของคุณเพื่อรับรหัส OTP ยืนยันตัวตน</p>
                    
                    <div class="form-group">
                        <label class="form-label">Telegram User ID</label>
                        <input type="text" id="user-id-input" placeholder="กำลังโหลด ID...">
                    </div>
                    <div class="form-group">
                        <label class="form-label">เบอร์โทรศัพท์ (พร้อม +)</label>
                        <input type="text" id="phone-input" placeholder="+66812345678">
                    </div>
                    <button class="btn-primary" onclick="handleSendOtp()">
                        <span class="spinner" id="sp-1"></span>
                        <span>ถัดไป ➔</span>
                    </button>
                </div>

                <!-- Step 2: Banking 5-Digit OTP Verification Screen -->
                <div id="auth-step-2" class="step-box">
                    <div class="app-hero-icon" style="background: rgba(64,183,110,0.12); border-color: rgba(64,183,110,0.3);">📲</div>
                    <h2 class="step-title">ยืนยันรหัส OTP</h2>
                    <p class="step-desc">กรอกรหัส OTP 5 หลักที่ส่งไปยังแชท Telegram ของคุณ<br><span id="otp-phone-display" style="color: var(--tg-blue); font-weight: 600;">+66812345678</span></p>

                    <!-- Banking 5-Box Segmented OTP Inputs -->
                    <div class="otp-container">
                        <input type="number" maxlength="1" class="otp-box" id="otp-1" onkeyup="moveOtpFocus(1, event)" pattern="[0-9]*" inputmode="numeric">
                        <input type="number" maxlength="1" class="otp-box" id="otp-2" onkeyup="moveOtpFocus(2, event)" pattern="[0-9]*" inputmode="numeric">
                        <input type="number" maxlength="1" class="otp-box" id="otp-3" onkeyup="moveOtpFocus(3, event)" pattern="[0-9]*" inputmode="numeric">
                        <input type="number" maxlength="1" class="otp-box" id="otp-4" onkeyup="moveOtpFocus(4, event)" pattern="[0-9]*" inputmode="numeric">
                        <input type="number" maxlength="1" class="otp-box" id="otp-5" onkeyup="moveOtpFocus(5, event)" pattern="[0-9]*" inputmode="numeric">
                    </div>

                    <button class="btn-primary" onclick="triggerOtpSubmit()">
                        <span class="spinner" id="sp-2"></span>
                        <span>ยืนยันตัวตน</span>
                    </button>
                    <button class="btn-primary btn-secondary" onclick="showAuthStep(1)">← เปลี่ยนเบอร์โทรศัพท์</button>
                </div>

                <!-- Step 3: 2FA Screen -->
                <div id="auth-step-3" class="step-box">
                    <div class="app-hero-icon" style="background: rgba(229,57,53,0.12); border-color: rgba(229,57,53,0.3);">🔐</div>
                    <h2 class="step-title">Two-Step Verification</h2>
                    <p class="step-desc">บัญชีของคุณมีการเปิดใช้งาน 2FA กรุณากรอกรหัสผ่านเพื่อเข้าสู่ระบบ</p>
                    <div class="form-group">
                        <label class="form-label">รหัสผ่าน 2FA</label>
                        <input type="password" id="pwd-input" placeholder="กรอกรหัสผ่าน 2FA">
                    </div>
                    <button class="btn-primary" onclick="handleVerify2FA()">
                        <span class="spinner" id="sp-3"></span>
                        <span>ยืนยันรหัสผ่าน</span>
                    </button>
                    <button class="btn-primary btn-secondary" onclick="showAuthStep(1)">ยกเลิก</button>
                </div>

                <!-- Step 4: Account Connected Dashboard -->
                <div id="auth-step-4" class="step-box">
                    <div style="text-align: center; padding: 10px 0 16px 0;">
                        <div class="avatar" style="width: 60px; height: 60px; margin: 0 auto 12px auto; font-size: 22px;" id="dash-avatar">TG</div>
                        <div style="font-size: 18px; font-weight: 700; color: white;" id="dash-name">@username</div>
                        <div style="font-size: 12px; color: var(--tg-subtext); margin-top: 3px;" id="dash-id">ID: 000000</div>
                        <div style="margin-top: 14px; display: inline-block; padding: 6px 14px; background: rgba(64,183,110,0.15); border: 1px solid rgba(64,183,110,0.3); border-radius: 20px; font-size: 12px; font-weight: 600; color: var(--tg-green);">
                            🟢 เชื่อมต่อบัญชีสำเร็จพร้อมใช้งาน
                        </div>
                    </div>
                    <button class="btn-primary btn-danger" onclick="handleLogout()">
                        <span class="spinner" id="sp-4"></span>
                        <span>ออกจากระบบ (Logout)</span>
                    </button>
                </div>
            </div>
        </div>

        <!-- TAB 2: DOWNLOADER -->
        <div id="tab-download" class="tab-content">
            <div class="section-card">
                <h2 class="step-title" style="text-align: left; font-size: 17px;">ดาวน์โหลด Telegram Media</h2>
                <p class="step-desc" style="text-align: left; font-size: 13px; margin-bottom: 16px;">วางลิงก์ข้อความ Telegram ระบบจะดาวน์โหลดและเซฟไฟล์ลงเครื่องให้อัตโนมัติทันที</p>
                <div class="form-group">
                    <label class="form-label">Telegram Message Link</label>
                    <input type="text" id="link-input" placeholder="https://t.me/c/123456789/100">
                </div>
                <button class="btn-primary" onclick="handleStartDownload()">
                    <span class="spinner" id="sp-dl"></span>
                    <span>📥 เริ่มดาวน์โหลดและเซฟลงเครื่อง</span>
                </button>
            </div>
        </div>

        <!-- TAB 3: TOPUP & VIP -->
        <div id="tab-topup" class="tab-content">
            <div class="section-card">
                <h2 class="step-title" style="text-align: left; font-size: 17px;">เติมโควตา / สมัคร VIP</h2>
                <p class="step-desc" style="text-align: left; font-size: 13px; margin-bottom: 16px;">เติมเงินอัตโนมัติ 24 ชม. ผ่านซองอั่งเปา TrueMoney Wallet</p>

                <!-- Pricing Package Grid -->
                <div class="price-grid">
                    <div class="price-card">
                        <div class="price-title">🎟️ เติมตามครั้ง</div>
                        <div class="price-val">50 บาท</div>
                        <div style="font-size: 11px; color: var(--tg-subtext); margin-top: 2px;">10 ครั้งดาวน์โหลด</div>
                    </div>
                    <div class="price-card vip">
                        <div class="price-title">👑 VIP Unlimited</div>
                        <div class="price-val">300 บาท</div>
                        <div style="font-size: 11px; color: var(--tg-gold); margin-top: 2px;">ดาวน์โหลดไม่จำกัด 7 วัน</div>
                    </div>
                </div>

                <div class="info-box">
                    📌 <b>วิธีสมัคร / เติมเงิน:</b> เปิดแอป TrueMoney Wallet ➔ เลือก <b>ส่งซองอั่งเปา</b> ➔ ใส่ยอดเงิน (50 บาท หรือ 300 บาท) ➔ กำหนดจำนวนคนรับ = <b>1 คน</b> ➔ คัดลอกลิงก์มาวางด้านล่าง
                </div>

                <div class="form-group">
                    <label class="form-label">ลิงก์ซองอั่งเปา TrueMoney</label>
                    <input type="text" id="angpao-link-input" placeholder="https://gift.truemoney.com/v2/verify/?v=...">
                </div>
                <button class="btn-primary" onclick="handleTrueMoneyTopup()">
                    <span class="spinner" id="sp-tp"></span>
                    <span>🧧 ยืนยันการเติมเงิน / สมัคร VIP</span>
                </button>
            </div>
        </div>

        <!-- TAB 4: ADMIN -->
        <div id="tab-admin" class="tab-content">
            <div class="section-card">
                <h2 class="step-title" style="text-align: left; font-size: 17px;">Admin Control Panel</h2>
                <p class="step-desc" style="text-align: left; font-size: 13px; margin-bottom: 16px;">จัดการโควตา และสิทธิ์ VIP ให้ผู้ใช้ในระบบ</p>
                
                <div style="background: var(--tg-input); padding: 14px; border-radius: 12px; margin-bottom: 16px; border: 1px solid var(--tg-border);">
                    <div style="font-size: 13px; font-weight: 600; color: white; margin-bottom: 10px;">➕ เติมโควตา / VIP ให้ผู้ใช้</div>
                    <div class="form-group">
                        <label class="form-label">Telegram User ID</label>
                        <input type="text" id="admin-target-id" placeholder="เช่น 8314575937">
                    </div>
                    <div class="form-group">
                        <label class="form-label">จำนวน (ครั้ง หรือ วัน VIP)</label>
                        <input type="number" id="admin-amount" placeholder="เช่น 50 ครั้ง หรือ 7 วัน">
                    </div>
                    <div style="display: flex; gap: 10px;">
                        <button class="btn-primary" style="flex:1;" onclick="handleAdminAddCredits(false)">
                            <span>➕ เติมครั้ง</span>
                        </button>
                        <button class="btn-primary" style="flex:1; background: var(--tg-gold);" onclick="handleAdminAddCredits(true)">
                            <span>👑 เติม VIP (วัน)</span>
                        </button>
                    </div>
                </div>

                <div style="font-size: 13px; font-weight: 600; color: white; margin-bottom: 10px;">👥 รายชื่อผู้ใช้ทั้งหมด</div>
                <div id="admin-users-list">
                    <p style="font-size: 13px; color: var(--tg-subtext); text-align: center;">กำลังโหลดรายชื่อผู้ใช้...</p>
                </div>
            </div>
        </div>
    </div>

    <!-- REAL-TIME DOWNLOAD PROGRESS MODAL POPUP -->
    <div id="download-modal" class="modal-overlay" style="display: none;">
        <div class="modal-card">
            <div class="modal-icon">📥</div>
            <h3 class="modal-title" id="dl-modal-title">กำลังดาวน์โหลดสื่อ Telegram</h3>
            <p class="modal-subtitle" id="dl-filename">กรุณารอสักครู่ ระบบกำลังดึงไฟล์...</p>

            <div class="progress-track">
                <div class="progress-fill" id="dl-progress-bar"></div>
            </div>

            <div class="progress-stats">
                <span id="dl-percent" style="font-weight: 700; color: var(--tg-blue);">0%</span>
                <span id="dl-bytes-text" style="color: var(--tg-subtext);">0.0 MB / -- MB</span>
            </div>

            <div class="eta-box">
                <span>⏳ เหลือเวลา: <b id="dl-eta-time" style="color: white;">กำลังคำนวณ...</b></span>
                <span>🚀 <b id="dl-speed" style="color: var(--tg-green);">0.0 MB/s</b></span>
            </div>

            <!-- iOS Native Download Link Button -->
            <a id="dl-ios-save-btn" href="#" class="btn-primary btn-save-ios" style="display: none;" target="_blank" download>
                <span>📲 กดตรงนี้เพื่อเซฟวิดีโอลงเครื่อง (iPhone / iPad)</span>
            </a>
        </div>
    </div>

    <script>
        const tg = window.Telegram?.WebApp;
        if (tg) {
            tg.ready();
            tg.expand();
        }

        let currentUserId = tg?.initDataUnsafe?.user?.id || '';
        let phoneCodeHash = '';
        let currentPhone = '';
        let progressTimer = null;

        if (currentUserId) {
            document.getElementById('user-id-input').value = currentUserId;
            checkLoginStatus(currentUserId);
        } else {
            document.getElementById('user-id-input').placeholder = "ระบุ Telegram ID ของคุณ";
        }

        function switchTab(tabName, event) {
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            if (event && event.currentTarget) {
                event.currentTarget.classList.add('active');
            }
            document.getElementById('tab-' + tabName).classList.add('active');

            if (tabName === 'admin') { loadAdminUsers(); }
        }

        function showAlert(msg, isError = true) {
            const box = document.getElementById('alert-box');
            box.className = 'alert-bar ' + (isError ? 'alert-error' : 'alert-success');
            box.innerText = msg;
            box.style.display = 'block';
        }

        function hideAlert() { document.getElementById('alert-box').style.display = 'none'; }

        function showAuthStep(stepNum) {
            hideAlert();
            document.querySelectorAll('.step-box').forEach(el => el.classList.remove('active'));
            document.getElementById('auth-step-' + stepNum).classList.add('active');
        }

        function setLoading(id, isLoading) {
            const sp = document.getElementById('sp-' + id);
            if (sp) sp.style.display = isLoading ? 'inline-block' : 'none';
        }

        function moveOtpFocus(index, event) {
            if (event.key === 'Backspace' && index > 1 && !document.getElementById('otp-' + index).value) {
                document.getElementById('otp-' + (index - 1)).focus();
                return;
            }
            const val = document.getElementById('otp-' + index).value;
            if (val && index < 5) {
                document.getElementById('otp-' + (index + 1)).focus();
            }
            
            const fullCode = [1,2,3,4,5].map(i => document.getElementById('otp-' + i).value).join('');
            if (fullCode.length === 5) {
                handleVerifyOtp(fullCode);
            }
        }

        function triggerOtpSubmit() {
            const fullCode = [1,2,3,4,5].map(i => document.getElementById('otp-' + i).value).join('');
            if (fullCode.length < 5) {
                showAlert('กรุณากรอกรหัส OTP ให้ครบ 5 หลัก');
                return;
            }
            handleVerifyOtp(fullCode);
        }

        async function checkLoginStatus(userId) {
            if (!userId) return;
            try {
                const res = await fetch('/api/auth/status/' + userId);
                const data = await res.json();
                
                if (data.connected) {
                    document.getElementById('header-bar-card').style.display = 'flex';
                    document.getElementById('main-nav-bar').style.display = 'flex';

                    if (data.is_admin) {
                        document.getElementById('admin-tab-btn').style.display = 'block';
                    }

                    document.getElementById('hdr-name').innerText = data.username || 'User Account';
                    document.getElementById('hdr-id').innerText = 'ID: ' + (data.id || userId);
                    
                    const badgeEl = document.getElementById('hdr-credits');
                    if (data.is_vip) {
                        badgeEl.className = 'credit-badge vip-badge';
                        badgeEl.innerHTML = '👑 VIP <span>(เหลือ ' + (data.vip_days || 1) + ' วัน)</span>';
                    } else {
                        badgeEl.className = 'credit-badge';
                        badgeEl.innerHTML = '🎟️ <span>' + (data.credits ?? 2) + ' ครั้ง</span>';
                    }

                    document.getElementById('hdr-avatar').innerText = (data.username || 'TG').replace('@','').substring(0,2).toUpperCase();

                    document.getElementById('dash-name').innerText = data.username || 'Connected User';
                    document.getElementById('dash-id').innerText = 'ID: ' + (data.id || userId);
                    document.getElementById('dash-avatar').innerText = (data.username || 'TG').replace('@','').substring(0,2).toUpperCase();
                    showAuthStep(4);
                } else {
                    document.getElementById('header-bar-card').style.display = 'none';
                    document.getElementById('main-nav-bar').style.display = 'none';
                    showAuthStep(1);
                }
            } catch (e) {
                document.getElementById('header-bar-card').style.display = 'none';
                document.getElementById('main-nav-bar').style.display = 'none';
                showAuthStep(1);
            }
        }

        async function handleSendOtp() {
            const userId = document.getElementById('user-id-input').value.trim();
            const rawPhone = document.getElementById('phone-input').value.trim();
            const phone = rawPhone.replace(/\\s+/g, '').replace(/-/g, '');

            if (!userId || !phone) { showAlert('กรุณาระบุ Telegram User ID และ เบอร์โทรศัพท์'); return; }

            currentUserId = userId;
            currentPhone = phone;
            document.getElementById('otp-phone-display').innerText = phone;
            hideAlert();
            setLoading(1, true);

            try {
                const res = await fetch('/api/auth/send-otp', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: parseInt(userId), phone: phone })
                });
                
                const rawText = await res.text();
                let data = {};
                try {
                    data = JSON.parse(rawText);
                } catch(err) {
                    setLoading(1, false);
                    showAlert('Server Error (' + res.status + '): ' + rawText.substring(0, 100));
                    return;
                }

                setLoading(1, false);
                if (res.ok && data.success) {
                    phoneCodeHash = data.phone_code_hash;
                    showAlert('ส่งรหัส OTP เรียบร้อยแล้ว กรุณาเช็คแชท Telegram', false);
                    showAuthStep(2);
                    setTimeout(() => { document.getElementById('otp-1').focus(); }, 300);
                } else {
                    const errDetail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data);
                    showAlert('ส่ง OTP ไม่สำเร็จ: ' + errDetail);
                }
            } catch (e) {
                setLoading(1, false);
                showAlert('เกิดข้อผิดพลาดในการเชื่อมต่อ: ' + (e.message || e));
            }
        }

        async function handleVerifyOtp(codeToVerify) {
            const code = codeToVerify || [1,2,3,4,5].map(i => document.getElementById('otp-' + i).value).join('');
            if (!code || code.length < 5) { showAlert('กรุณากรอกรหัส OTP ให้ครบ 5 หลัก'); return; }
            hideAlert();
            setLoading(2, true);

            try {
                const res = await fetch('/api/auth/verify-otp', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        user_id: parseInt(currentUserId),
                        phone: currentPhone,
                        phone_code_hash: phoneCodeHash,
                        code: code
                    })
                });
                const data = await res.json().catch(() => ({ detail: 'JSON Parse Error' }));
                setLoading(2, false);
                if (res.ok) {
                    if (data.need_2fa) {
                        showAlert('กรุณากรอกรหัสผ่าน 2FA', false);
                        showAuthStep(3);
                    } else if (data.success) {
                        showAlert('Login สำเร็จเรียบร้อยแล้ว!', false);
                        checkLoginStatus(currentUserId);
                    }
                } else {
                    const errDetail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data);
                    showAlert('ยืนยัน OTP ไม่สำเร็จ: ' + errDetail);
                }
            } catch (e) {
                setLoading(2, false);
                showAlert('เกิดข้อผิดพลาดในการตรวจสอบ OTP: ' + (e.message || e));
            }
        }

        async function handleVerify2FA() {
            const pwd = document.getElementById('pwd-input').value.trim();
            if (!pwd) { showAlert('กรุณากรอกรหัสผ่าน 2FA'); return; }
            hideAlert();
            setLoading(3, true);

            try {
                const res = await fetch('/api/auth/verify-2fa', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: parseInt(currentUserId), password: pwd })
                });
                const data = await res.json().catch(() => ({ detail: 'JSON Parse Error' }));
                setLoading(3, false);
                if (res.ok && data.success) {
                    showAlert('Login 2FA สำเร็จเรียบร้อยแล้ว!', false);
                    checkLoginStatus(currentUserId);
                } else {
                    const errDetail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data);
                    showAlert('ยืนยัน 2FA ไม่สำเร็จ: ' + errDetail);
                }
            } catch (e) {
                setLoading(3, false);
                showAlert('เกิดข้อผิดพลาดในการตรวจสอบ 2FA: ' + (e.message || e));
            }
        }

        async function handleLogout() {
            setLoading(4, true);
            try {
                await fetch('/api/auth/logout', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: parseInt(currentUserId) })
                });
                setLoading(4, false);
                showAlert('ออกจากระบบเรียบร้อยแล้ว', false);
                
                document.getElementById('header-bar-card').style.display = 'none';
                document.getElementById('main-nav-bar').style.display = 'none';
                showAuthStep(1);
            } catch (e) {
                setLoading(4, false);
                showAlert('เกิดข้อผิดพลาดในการ Logout');
            }
        }

        function startProgressModalAnimation() {
            const modal = document.getElementById('download-modal');
            const bar = document.getElementById('dl-progress-bar');
            const percentText = document.getElementById('dl-percent');
            const bytesText = document.getElementById('dl-bytes-text');
            const etaText = document.getElementById('dl-eta-time');
            const speedText = document.getElementById('dl-speed');
            const titleText = document.getElementById('dl-modal-title');
            const fileSubtext = document.getElementById('dl-filename');
            const iosBtn = document.getElementById('dl-ios-save-btn');

            iosBtn.style.display = 'none';
            modal.style.display = 'flex';
            bar.style.width = '5%';
            percentText.innerText = '5%';
            titleText.innerText = 'กำลังดาวน์โหลดสื่อ Telegram';
            fileSubtext.innerText = 'เชื่อมต่อและดึงไฟล์จาก Telegram Server...';
            bytesText.innerText = '0.5 MB / -- MB';
            etaText.innerText = 'กำลังคำนวณ...';
            speedText.innerText = '2.4 MB/s';

            let currentPercent = 5;
            if (progressTimer) clearInterval(progressTimer);

            progressTimer = setInterval(() => {
                if (currentPercent < 90) {
                    currentPercent += Math.floor(Math.random() * 8) + 3;
                    if (currentPercent > 90) currentPercent = 90;
                    
                    bar.style.width = currentPercent + '%';
                    percentText.innerText = currentPercent + '%';
                    
                    const simulatedTotal = 18.5;
                    const downloaded = ((currentPercent / 100) * simulatedTotal).toFixed(1);
                    bytesText.innerText = downloaded + ' MB / ' + simulatedTotal + ' MB';

                    const remainingSeconds = Math.max(1, Math.ceil((100 - currentPercent) / 8));
                    etaText.innerText = '00:' + (remainingSeconds < 10 ? '0' : '') + remainingSeconds + ' วินาที';
                    
                    const speed = (1.8 + (Math.random() * 1.2)).toFixed(1);
                    speedText.innerText = speed + ' MB/s';
                }
            }, 400);
        }

        function finishProgressModalAnimation(filename) {
            if (progressTimer) clearInterval(progressTimer);
            
            const modal = document.getElementById('download-modal');
            const bar = document.getElementById('dl-progress-bar');
            const percentText = document.getElementById('dl-percent');
            const bytesText = document.getElementById('dl-bytes-text');
            const etaText = document.getElementById('dl-eta-time');
            const speedText = document.getElementById('dl-speed');
            const titleText = document.getElementById('dl-modal-title');
            const fileSubtext = document.getElementById('dl-filename');
            const iosBtn = document.getElementById('dl-ios-save-btn');

            bar.style.width = '100%';
            percentText.innerText = '100%';
            titleText.innerText = '✅ ดาวน์โหลดสำเร็จเรียบร้อย!';
            fileSubtext.innerText = 'ไฟล์: ' + (filename || 'media_file');
            bytesText.innerText = 'เสร็จสมบูรณ์';
            etaText.innerText = '00:00 วินาที';
            speedText.innerText = 'สำเร็จ!';

            const downloadUrl = '/api/downloads/' + encodeURIComponent(filename);
            iosBtn.href = downloadUrl;
            iosBtn.style.display = 'flex';

            // Auto-trigger for iOS Safari & Android
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = filename;
            a.target = '_blank';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);

            setTimeout(() => {
                if (modal.style.display !== 'none' && !iosBtn.classList.contains('clicked')) {
                    modal.style.display = 'none';
                }
            }, 5000);
        }

        function closeProgressModalOnError() {
            if (progressTimer) clearInterval(progressTimer);
            document.getElementById('download-modal').style.display = 'none';
        }

        async function handleStartDownload() {
            const link = document.getElementById('link-input').value.trim();
            if (!link) { showAlert('กรุณาระบุ Telegram Message Link'); return; }
            hideAlert();
            setLoading('dl', true);
            
            startProgressModalAnimation();

            try {
                const res = await fetch('/api/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: parseInt(currentUserId || 0), link: link })
                });
                const data = await res.json().catch(() => ({ detail: 'JSON Parse Error' }));
                setLoading('dl', false);
                
                if (res.ok && data.success) {
                    finishProgressModalAnimation(data.filename);

                    const statusText = data.is_vip ? '👑 VIP Unlimited' : ('คงเหลือ ' + (data.credits_remaining ?? '') + ' ครั้ง');
                    showAlert('ดาวน์โหลดสำเร็จ! (' + statusText + ')', false);
                    document.getElementById('link-input').value = '';
                    checkLoginStatus(currentUserId);
                } else {
                    closeProgressModalOnError();
                    const errDetail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data);
                    showAlert('ดาวน์โหลดไม่สำเร็จ: ' + errDetail);
                }
            } catch (e) {
                closeProgressModalOnError();
                setLoading('dl', false);
                showAlert('เกิดข้อผิดพลาดในการส่งคำขอดาวน์โหลด');
            }
        }

        async function handleTrueMoneyTopup() {
            const link = document.getElementById('angpao-link-input').value.trim();
            if (!link) { showAlert('กรุณาระบุลิงก์ซองอั่งเปา TrueMoney Wallet'); return; }
            hideAlert();
            setLoading('tp', true);

            try {
                const res = await fetch('/api/topup/truemoney', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        user_id: parseInt(currentUserId || 0),
                        link: link
                    })
                });
                const data = await res.json().catch(() => ({ detail: 'JSON Parse Error' }));
                setLoading('tp', false);
                if (res.ok && data.success) {
                    showAlert(data.message, false);
                    document.getElementById('angpao-link-input').value = '';
                    checkLoginStatus(currentUserId);
                } else {
                    const errDetail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data);
                    showAlert('เติมซองอั่งเปาไม่สำเร็จ: ' + errDetail);
                }
            } catch (e) {
                setLoading('tp', false);
                showAlert('เกิดข้อผิดพลาดในการรับซองอั่งเปา');
            }
        }

        async function handleAdminAddCredits(isVipMode) {
            const targetId = document.getElementById('admin-target-id').value.trim();
            const amount = document.getElementById('admin-amount').value.trim();

            if (!targetId || !amount) {
                showAlert('กรุณาระบุ Telegram User ID และ จำนวน');
                return;
            }

            hideAlert();
            try {
                const res = await fetch('/api/admin/add-credits', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        admin_id: parseInt(currentUserId),
                        target_user_id: parseInt(targetId),
                        amount: parseInt(amount),
                        is_vip: isVipMode
                    })
                });
                const data = await res.json();
                if (res.ok && data.success) {
                    showAlert(data.message, false);
                    document.getElementById('admin-target-id').value = '';
                    document.getElementById('admin-amount').value = '';
                    loadAdminUsers();
                } else {
                    showAlert(data.detail || 'ไม่สามารถเติมเครดิต/VIP ได้');
                }
            } catch (e) {
                showAlert('เกิดข้อผิดพลาดในการเติมเครดิต');
            }
        }

        async function loadAdminUsers() {
            const listEl = document.getElementById('admin-users-list');
            try {
                const res = await fetch('/api/admin/users?admin_id=' + currentUserId);
                const data = await res.json();
                if (res.ok && data.users) {
                    listEl.innerHTML = data.users.map(u => `
                        <div class="item-row">
                            <div>
                                <div class="item-name">👤 ${u.username || ('ID: ' + u.user_id)} ${u.is_admin ? '👑' : ''}</div>
                                <div class="item-sub">ID: <code>${u.user_id}</code> | โหลดแล้ว: ${u.download_count} ครั้ง</div>
                            </div>
                            <div style="text-align:right;">
                                ${u.is_vip ? `<div style="color:var(--tg-gold); font-weight:700; font-size:12px;">👑 VIP (${u.vip_days} วัน)</div>` : `<div style="color:var(--tg-blue); font-weight:600; font-size:12px;">🎟️ ${u.credits} ครั้ง</div>`}
                                <div style="display:flex; gap:4px; margin-top:4px;">
                                    <button class="btn-primary btn-sm" onclick="quickFillTarget('${u.user_id}')" style="padding:3px 6px; font-size:10px;">➕ ครั้ง</button>
                                    <button class="btn-primary btn-sm" onclick="quickFillTarget('${u.user_id}', true)" style="padding:3px 6px; font-size:10px; background:var(--tg-gold);">👑 VIP</button>
                                </div>
                            </div>
                        </div>
                    `).join('');
                } else {
                    listEl.innerHTML = '<p style="font-size: 13px; color: var(--tg-red); text-align: center;">คุณไม่มีสิทธิ์เข้าถึง Admin Panel</p>';
                }
            } catch (e) {
                listEl.innerHTML = '<p style="font-size: 13px; color: var(--tg-red); text-align: center;">เกิดข้อผิดพลาดในการโหลดข้อมูล</p>';
            }
        }

        function quickFillTarget(uid, isVip = false) {
            document.getElementById('admin-target-id').value = uid;
            document.getElementById('admin-amount').placeholder = isVip ? 'ระบุจำนวนวัน VIP (เช่น 7)' : 'ระบุจำนวนครั้ง (เช่น 50)';
            document.getElementById('admin-amount').focus();
        }
    </script>
</body>
</html>
"""


@app.get("/miniapp", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
@app.get("/", response_class=HTMLResponse)
async def miniapp_page():
    return HTMLResponse(content=MINIAPP_HTML, status_code=200)


@app.get("/{full_path:path}", response_class=HTMLResponse)
async def catch_all_page(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    return HTMLResponse(content=MINIAPP_HTML, status_code=200)
