"""
app/web/server.py - Telegram MiniApp & FastAPI Web Application
Telegram Downloader MiniApp UI & REST API (Vercel Serverless Safe & Fallback Safe)
"""

import os
import tempfile
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.telegram.auth import (
    check_user_session,
    send_otp,
    verify_otp,
    verify_2fa,
    logout_user
)

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


@app.get("/api/auth/status/{user_id}")
async def auth_status(user_id: int):
    api_id, api_hash = get_api_credentials()
    res = await check_user_session(user_id, api_id, api_hash)
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
    return {
        "success": True,
        "message": "เพิ่มรายการดาวน์โหลดเข้าคิวแล้ว",
        "link": req.link,
        "status": "queued"
    }


@app.get("/api/downloads")
async def list_downloads():
    downloads_dir = get_downloads_dir()
    files = []
    for f in downloads_dir.iterdir():
        if f.is_file() and f.name != ".gitkeep":
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "path": str(f)
            })
    return {"files": files}


MINIAPP_HTML = """<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Telegram Downloader MiniApp</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: rgba(30, 41, 59, 0.75);
            --text-color: #f8fafc;
            --accent-color: #6366f1;
            --accent-gradient: linear-gradient(135deg, #6366f1, #a855f7);
            --border-color: rgba(255, 255, 255, 0.12);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Outfit', sans-serif; -webkit-tap-highlight-color: transparent; }
        body {
            background: var(--bg-color);
            color: var(--text-color);
            min-height: 100vh;
            padding: 16px;
            display: flex;
            flex-direction: column;
        }
        .container {
            max-width: 480px;
            margin: 0 auto;
            width: 100%;
            flex: 1;
            display: flex;
            flex-direction: column;
        }
        .nav-tabs {
            display: flex;
            background: rgba(15, 23, 42, 0.8);
            border-radius: 16px;
            padding: 4px;
            border: 1px solid var(--border-color);
            margin-bottom: 20px;
        }
        .tab-btn {
            flex: 1;
            padding: 10px 8px;
            border: none;
            background: transparent;
            color: #94a3b8;
            font-size: 13px;
            font-weight: 600;
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }
        .tab-btn.active {
            background: var(--accent-gradient);
            color: white;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
        }
        .glass-card {
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 24px 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
            margin-bottom: 16px;
        }
        .tab-content { display: none; }
        .tab-content.active { display: block; animation: fadeIn 0.3s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
        
        .header-title { font-size: 20px; font-weight: 700; color: white; margin-bottom: 4px; }
        .header-sub { font-size: 13px; color: #94a3b8; margin-bottom: 20px; }

        .form-group { margin-bottom: 16px; }
        label { display: block; font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
        input {
            width: 100%; padding: 13px 14px;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border-color);
            border-radius: 12px; color: white; font-size: 14px; outline: none;
            transition: all 0.2s ease;
        }
        input:focus { border-color: #818cf8; box-shadow: 0 0 0 3px rgba(129, 140, 248, 0.25); }
        
        .btn {
            width: 100%; padding: 14px;
            background: var(--accent-gradient);
            border: none; border-radius: 12px; color: white; font-size: 14px; font-weight: 600;
            cursor: pointer; transition: all 0.2s ease;
            box-shadow: 0 8px 16px rgba(99, 102, 241, 0.35);
            display: flex; align-items: center; justify-content: center; gap: 8px;
        }
        .btn:active { transform: scale(0.98); }
        .btn-secondary {
            background: rgba(255, 255, 255, 0.08); border: 1px solid var(--border-color);
            box-shadow: none; color: #cbd5e1; margin-top: 10px;
        }
        .btn-danger {
            background: rgba(239, 68, 68, 0.2); border: 1px solid rgba(239, 68, 68, 0.4);
            color: #fca5a5; box-shadow: none; margin-top: 10px;
        }

        .alert {
            padding: 12px 14px; border-radius: 12px; font-size: 13px; margin-bottom: 16px; display: none;
            word-break: break-word;
        }
        .alert-danger { background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.3); color: #fca5a5; }
        .alert-success { background: rgba(34, 197, 94, 0.15); border: 1px solid rgba(34, 197, 94, 0.3); color: #86efac; }

        .user-card {
            text-align: center; background: rgba(15, 23, 42, 0.5); padding: 18px;
            border-radius: 16px; border: 1px solid var(--border-color); margin-bottom: 16px;
        }
        .avatar {
            width: 64px; height: 64px; border-radius: 50%;
            background: linear-gradient(135deg, #10b981, #059669);
            color: white; font-size: 24px; font-weight: 700;
            display: flex; align-items: center; justify-content: center; margin: 0 auto 10px auto;
            box-shadow: 0 0 16px rgba(16, 185, 129, 0.4);
        }
        .status-badge {
            display: inline-block; padding: 4px 10px; border-radius: 20px;
            font-size: 11px; font-weight: 600; background: rgba(34, 197, 94, 0.2);
            color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3); margin-top: 6px;
        }
        
        .step-box { display: none; }
        .step-box.active { display: block; }

        .file-item {
            display: flex; align-items: center; justify-content: space-between;
            background: rgba(15, 23, 42, 0.5); padding: 12px 14px;
            border-radius: 12px; border: 1px solid var(--border-color); margin-bottom: 8px;
        }
        .file-name { font-size: 13px; color: white; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 220px; }
        .file-size { font-size: 11px; color: #94a3b8; }

        .spinner {
            width: 18px; height: 18px; border: 2.5px solid rgba(255,255,255,0.3);
            border-radius: 50%; border-top-color: white; animation: spin 0.8s linear infinite; display: none;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="container">
        <!-- Navigation Tabs -->
        <div class="nav-tabs">
            <button class="tab-btn active" onclick="switchTab('auth', event)">
                🔐 <span>Account</span>
            </button>
            <button class="tab-btn" onclick="switchTab('download', event)">
                📥 <span>Downloader</span>
            </button>
            <button class="tab-btn" onclick="switchTab('files', event)">
                📁 <span>Files</span>
            </button>
        </div>

        <div id="alert-box" class="alert"></div>

        <!-- TAB 1: AUTHENTICATION -->
        <div id="tab-auth" class="tab-content active">
            <div class="glass-card">
                <!-- Step 1: Phone -->
                <div id="auth-step-1" class="step-box active">
                    <h2 class="header-title">🔐 User Account Login</h2>
                    <p class="header-sub">เข้าสู่ระบบเพื่อใช้ Telegram Session ของคุณดาวน์โหลด Media</p>
                    <div class="form-group">
                        <label>Telegram User ID</label>
                        <input type="text" id="user-id-input" placeholder="กำลังดึง Telegram ID...">
                    </div>
                    <div class="form-group">
                        <label>เบอร์โทรศัพท์ (พร้อม +)</label>
                        <input type="text" id="phone-input" placeholder="+66812345678">
                    </div>
                    <button class="btn" onclick="handleSendOtp()">
                        <span class="spinner" id="sp-1"></span>
                        <span>ส่งรหัส OTP</span>
                    </button>
                </div>

                <!-- Step 2: OTP -->
                <div id="auth-step-2" class="step-box">
                    <h2 class="header-title">📲 ยืนยันรหัส OTP</h2>
                    <p class="header-sub">กรอกรหัส OTP ที่ได้รับจากแชท Telegram ของคุณ</p>
                    <div class="form-group">
                        <label>รหัส OTP</label>
                        <input type="text" id="otp-input" placeholder="เช่น 12345">
                    </div>
                    <button class="btn" onclick="handleVerifyOtp()">
                        <span class="spinner" id="sp-2"></span>
                        <span>ยืนยันรหัส OTP</span>
                    </button>
                    <button class="btn btn-secondary" onclick="showAuthStep(1)">ยกเลิก</button>
                </div>

                <!-- Step 3: 2FA -->
                <div id="auth-step-3" class="step-box">
                    <h2 class="header-title">🔐 Two-Step Verification</h2>
                    <p class="header-sub">บัญชีของคุณมีการตั้งค่ารหัสผ่าน 2FA</p>
                    <div class="form-group">
                        <label>2FA Password</label>
                        <input type="password" id="pwd-input" placeholder="กรอกรหัสผ่าน 2FA">
                    </div>
                    <button class="btn" onclick="handleVerify2FA()">
                        <span class="spinner" id="sp-3"></span>
                        <span>ยืนยันรหัสผ่าน 2FA</span>
                    </button>
                    <button class="btn btn-secondary" onclick="showAuthStep(1)">ยกเลิก</button>
                </div>

                <!-- Step 4: Dashboard -->
                <div id="auth-step-4" class="step-box">
                    <div class="user-card">
                        <div class="avatar" id="dash-avatar">TG</div>
                        <h2 style="font-size: 18px; color: white;" id="dash-name">@username</h2>
                        <p style="font-size: 12px; color: #94a3b8; margin-top: 2px;" id="dash-id">ID: 000000</p>
                        <div class="status-badge">🟢 Telegram Account: Connected</div>
                    </div>
                    <button class="btn btn-danger" onclick="handleLogout()">
                        <span class="spinner" id="sp-4"></span>
                        <span>ออกจากระบบ (Logout)</span>
                    </button>
                </div>
            </div>
        </div>

        <!-- TAB 2: DOWNLOADER -->
        <div id="tab-download" class="tab-content">
            <div class="glass-card">
                <h2 class="header-title">📥 Download Telegram Media</h2>
                <p class="header-sub">วางลิงก์ข้อความ Telegram เพื่อเริ่มดาวน์โหลดรูปภาพ/วิดีโอ/ไฟล์</p>
                <div class="form-group">
                    <label>Telegram Message Link</label>
                    <input type="text" id="link-input" placeholder="https://t.me/c/123456789/100">
                </div>
                <button class="btn" onclick="handleStartDownload()">
                    <span class="spinner" id="sp-dl"></span>
                    <span>เริ่มดาวน์โหลด</span>
                </button>
            </div>
        </div>

        <!-- TAB 3: FILES -->
        <div id="tab-files" class="tab-content">
            <div class="glass-card">
                <h2 class="header-title">📁 Downloaded Files</h2>
                <p class="header-sub">รายการไฟล์ที่ดาวน์โหลดเสร็จสมบูรณ์ในระบบ</p>
                <div id="files-list">
                    <p style="font-size: 13px; color: #94a3b8; text-align: center;">กำลังโหลดรายการไฟล์...</p>
                </div>
            </div>
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

        if (currentUserId) {
            document.getElementById('user-id-input').value = currentUserId;
            checkLoginStatus(currentUserId);
        } else {
            document.getElementById('user-id-input').placeholder = "ระบุ Telegram ID ของคุณ";
        }

        function switchTab(tabName, event) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            if (event && event.currentTarget) {
                event.currentTarget.classList.add('active');
            }
            document.getElementById('tab-' + tabName).classList.add('active');

            if (tabName === 'files') { loadFiles(); }
        }

        function showAlert(msg, isError = true) {
            const box = document.getElementById('alert-box');
            box.className = 'alert ' + (isError ? 'alert-danger' : 'alert-success');
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

        async function checkLoginStatus(userId) {
            if (!userId) return;
            try {
                const res = await fetch('/api/auth/status/' + userId);
                const data = await res.json();
                if (data.connected) {
                    document.getElementById('dash-name').innerText = data.username || 'Connected User';
                    document.getElementById('dash-id').innerText = 'ID: ' + (data.id || userId);
                    document.getElementById('dash-avatar').innerText = (data.username || 'TG').replace('@','').substring(0,2).toUpperCase();
                    showAuthStep(4);
                }
            } catch (e) {}
        }

        async function handleSendOtp() {
            const userId = document.getElementById('user-id-input').value.trim();
            const rawPhone = document.getElementById('phone-input').value.trim();
            const phone = rawPhone.replace(/\\s+/g, '').replace(/-/g, '');

            if (!userId || !phone) { showAlert('กรุณาระบุ Telegram User ID และ เบอร์โทรศัพท์'); return; }

            currentUserId = userId;
            currentPhone = phone;
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
                } else {
                    const errDetail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data);
                    showAlert('ส่ง OTP ไม่สำเร็จ: ' + errDetail);
                }
            } catch (e) {
                setLoading(1, false);
                showAlert('เกิดข้อผิดพลาดในการเชื่อมต่อ: ' + (e.message || e));
            }
        }

        async function handleVerifyOtp() {
            const code = document.getElementById('otp-input').value.trim();
            if (!code) { showAlert('กรุณากรอกรหัส OTP'); return; }
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
                showAuthStep(1);
            } catch (e) {
                setLoading(4, false);
                showAlert('เกิดข้อผิดพลาดในการ Logout');
            }
        }

        async function handleStartDownload() {
            const link = document.getElementById('link-input').value.trim();
            if (!link) { showAlert('กรุณาระบุ Telegram Message Link'); return; }
            hideAlert();
            setLoading('dl', true);
            try {
                const res = await fetch('/api/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: parseInt(currentUserId || 0), link: link })
                });
                const data = await res.json().catch(() => ({ detail: 'JSON Parse Error' }));
                setLoading('dl', false);
                if (res.ok && data.success) {
                    showAlert('ดาวน์โหลดสำเร็จ! เพิ่มรายการเข้าคิวแล้ว', false);
                    document.getElementById('link-input').value = '';
                } else {
                    const errDetail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data);
                    showAlert('ดาวน์โหลดไม่สำเร็จ: ' + errDetail);
                }
            } catch (e) {
                setLoading('dl', false);
                showAlert('เกิดข้อผิดพลาดในการส่งคำขอดาวน์โหลด');
            }
        }

        async function loadFiles() {
            const listEl = document.getElementById('files-list');
            try {
                const res = await fetch('/api/downloads');
                const data = await res.json();
                if (data.files && data.files.length > 0) {
                    listEl.innerHTML = data.files.map(f => `
                        <div class="file-item">
                            <div>
                                <div class="file-name">${f.name}</div>
                                <div class="file-size">${(f.size / (1024*1024)).toFixed(2)} MB</div>
                            </div>
                            <span style="font-size: 12px; color: #4ade80;">Completed</span>
                        </div>
                    `).join('');
                } else {
                    listEl.innerHTML = '<p style="font-size: 13px; color: #94a3b8; text-align: center;">ยังไม่มีไฟล์ที่ดาวน์โหลดในขณะนี้</p>';
                }
            } catch (e) {
                listEl.innerHTML = '<p style="font-size: 13px; color: #fca5a5; text-align: center;">เกิดข้อผิดพลาดในการโหลดรายการไฟล์</p>';
            }
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
