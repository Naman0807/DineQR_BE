import secrets
import httpx
from fastapi import HTTPException
from app.config import get_settings
from app.utils.logger import logger

settings = get_settings()

# Development settings
DEV_PHONE_NUMBER = "9537112498"
DEV_OTP_CODE = "080706"


def generate_numeric_otp(length: int = 6) -> str:
    """Generate a secure, random numeric OTP of specified length."""
    return f"{secrets.randbelow(10**length):0{length}d}"


async def send_otp_sms(phone_number: str, otp_code: str) -> bool:
    """Send OTP using Fast2SMS API route.
    
    In development mode (when FAST2SMS_API_KEY is not set), 
    this prints the OTP to console instead of sending SMS.
    """
    if not settings.FAST2SMS_API_KEY:
        logger.warning("[OTP] Fast2SMS API Key not configured. Skipping actual SMS send.")
        print(f"--- MOCK SMS: OTP for {phone_number} is {otp_code} ---")
        return True

    url = "https://www.fast2sms.com/dev/bulkV2"
    payload = {
        "variables_values": otp_code,
        "route": "otp",
        "numbers": phone_number,
    }
    headers = {
        "authorization": settings.FAST2SMS_API_KEY,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if data.get("return") is True:
                    return True
                else:
                    logger.error(f"[OTP] Fast2SMS Error: {data.get('message')}")
                    return False
            return False
        except Exception as e:
            logger.error(f"[OTP] Request failed: {str(e)}")
            return False
