"""
app/services/truemoney.py - TrueMoney Wallet Angpao Voucher Auto Redemption API (Standard Library Safe)
"""

import re
import json
import asyncio
import urllib.request
import urllib.error


def extract_voucher_hash(url_or_code: str) -> str:
    """Extract voucher hash from TrueMoney gift URL."""
    if not url_or_code:
        return ""
    url_or_code = url_or_code.strip()
    match = re.search(r"v=([a-zA-Z0-9]+)", url_or_code)
    if match:
        return match.group(1)
    if len(url_or_code) >= 15 and "/" not in url_or_code:
        return url_or_code
    return ""


def _sync_redeem(phone: str, voucher_hash: str) -> tuple[bool, float, str]:
    url = f"https://gift.truemoney.com/v2/verify/{voucher_hash}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json"
    }
    payload = json.dumps({"mobile": phone, "voucher_hash": voucher_hash}).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))

            status_code = data.get("status", {}).get("code")
            if status_code == "SUCCESS":
                amount_str = data.get("data", {}).get("voucher", {}).get("amount_baht", "0")
                amount = float(amount_str)
                return True, amount, None
            elif status_code == "VOUCHER_OUT_OF_STOCK":
                return False, 0.0, "ซองอั่งเปานี้ถูกใช้แล้ว หรือมีผู้รับไปแล้ว"
            elif status_code == "VOUCHER_NOT_FOUND":
                return False, 0.0, "ไม่พบซองอั่งเปานี้ในระบบ TrueMoney"
            elif status_code == "VOUCHER_EXPIRED":
                return False, 0.0, "ซองอั่งเปานี้หมดอายุแล้ว"
            elif status_code == "CANNOT_GET_OWN_VOUCHER":
                return False, 0.0, "ไม่สามารถเติมซองอั่งเปาที่สร้างขึ้นเองได้"
            else:
                msg = data.get("status", {}).get("message", "เติมซองอั่งเปาไม่สำเร็จ")
                return False, 0.0, f"TrueMoney Error: {msg}"
    except urllib.error.HTTPError as e:
        try:
            err_data = json.loads(e.read().decode("utf-8"))
            msg = err_data.get("status", {}).get("message", str(e))
            return False, 0.0, f"TrueMoney Error: {msg}"
        except Exception:
            return False, 0.0, f"HTTP Error: {e.code}"
    except Exception as e:
        return False, 0.0, f"เกิดข้อผิดพลาดในการรับซองอั่งเปา: {str(e)}"


async def redeem_truemoney_angpao(mobile_number: str, voucher_link: str) -> tuple[bool, float, str]:
    """
    Redeem TrueMoney Angpao link automatically using standard library.
    Returns: (success: bool, amount_baht: float, error_msg: str)
    """
    voucher_hash = extract_voucher_hash(voucher_link)
    if not voucher_hash:
        return False, 0.0, "ลิงก์ซองอั่งเปา TrueMoney ไม่ถูกต้อง! ตัวอย่าง: https://gift.truemoney.com/v2/verify/?v=..."

    phone = mobile_number.strip().replace("-", "").replace(" ", "")
    if not phone or len(phone) < 10 or phone == "0800000000":
        return False, 0.0, "กรุณาตั้งค่าเบอร์ TrueMoney Wallet ของแอดมินในระบบก่อน"

    return await asyncio.to_thread(_sync_redeem, phone, voucher_hash)
