import requests
import os
from dotenv import load_dotenv

load_dotenv()

USERNAME = os.getenv('PAYAMAK_USERNAME')  # شماره کاربری پنل
API_KEY = os.getenv('PAYAMAK_API_KEY')    # کلید API که در پنل دیدی
FROM_NUMBER = os.getenv('PAYAMAK_FROM')   # شماره خط فرستنده مثل 1000xxxx

def send_sms(phone_number, message):
    url = "https://rest.payamak-panel.com/api/SendSMS/SendSMS"
    payload = {
        "username": USERNAME,
        "password": API_KEY,  # استفاده از APIKey به‌جای رمز عبور
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
        print("📨 پاسخ API:", data)

        if data.get("RetStatus") == 1:
            print("✅ پیامک با موفقیت ارسال شد.")
        else:
            print("❌ ارسال پیامک با خطا مواجه شد:", data.get("StrRetStatus"))

        return data
    except Exception as e:
        print(f"⚠️ خطا در ارسال پیامک: {e}")
        return False
