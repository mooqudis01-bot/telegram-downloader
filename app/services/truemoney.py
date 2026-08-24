"""
app/services/truemoney.py - TrueMoney Wallet Angpao Voucher Auto Redemption API
"""

import re
import httpx


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


async def redeem_truemoney_angpao(mobile_number: str, voucher_link: str) -> tuple[bool, float, str]:
    """
    Redeem TrueMoney Angpao link automatically.
    Returns: (success: bool, amount_baht: float, error_msg: str)
    """
    voucher_hash = extract_voucher_hash(voucher_link)
    if not voucher_hash:
        return False, 0.0, "ลิงก์ซองอั่งเปา TrueMoney ไม่ถูกต้อง! ตัวอย่าง: https://gift.truemoney.com/v2/verify/?v=..."

    phone = mobile_number.strip().replace("-", "").replace(" ", "")
    if not phone or len(phone) < 10:
        return False, 0.0, "กรุณาตั้งค่าเบอร์ TrueMoney Wallet ของแอดมินในระบบก่อน"

    url = f"https://gift.truemoney.com/v2/verify/{voucher_hash}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json"
    }
    payload = {
        "mobile": phone,
        "voucher_hash": voucher_hash
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=headers)
            data = res.json()

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
    except Exception as e:
        return False, 0.0, f"เกิดข้อผิดพลาดในการรับซองอั่งเปา: {str(e)}"
