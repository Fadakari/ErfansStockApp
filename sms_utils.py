import requests
import os
from dotenv import load_dotenv

load_dotenv()

USERNAME = os.getenv('PAYAMAK_USERNAME')
PASSWORD = os.getenv('PAYAMAK_PASSWORD')
FROM_NUMBER = os.getenv('PAYAMAK_FROM')

def send_sms(phone_number, message):
    url = "https://rest.payamak-panel.com/api/SendSMS/SendSMS"
    payload = {
        "username": USERNAME,
        "password": PASSWORD,
        "to": phone_number,
        "from": FROM_NUMBER,
        "text": message,
        "isflash": False
    }
    print(f"🔍 شماره ارسالی به API: [{phone_number}]")
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()

        data = response.json()
        print("📨 پاسخ API:", data)  # اینجا چاپ می‌کنه

        # بررسی موفقیت پیامک
        if data.get("RetStatus") == 1:
            print("✅ پیامک با موفقیت ارسال شد.")
        else:
            print("❌ ارسال پیامک با خطا مواجه شد:", data.get("StrRetStatus"))

        return data
    except Exception as e:
        print(f"⚠️ خطا در ارسال پیامک: {e}")
        return False
