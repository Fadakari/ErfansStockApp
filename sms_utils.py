import requests
import os
import logging
from dotenv import load_dotenv

# تنظیمات لاگ
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# لود کردن متغیرهای محیطی
load_dotenv()

USERNAME = os.getenv('PAYAMAK_USERNAME')
API_KEY = os.getenv('PAYAMAK_API_KEY')
PATTERN_CODE = os.getenv('PAYAMAK_PATTERN_CODE')  # باید عدد bodyId واقعی باشه

def send_verification_code(phone_number, code):
    logging.info(f"🛂 شروع ارسال کد: شماره={phone_number}, کد={code}")
    url = "https://rest.payamak-panel.com/api/SendSMS/BaseServiceNumber"

    payload = {
        "username": USERNAME,
        "password": API_KEY,
        "to": phone_number,
        "bodyId": PATTERN_CODE,
        "text": [str(code)]  # 👈 باید text باشه نه args
    }

    logging.debug(f"📦 داده‌ی ارسالی به ملی پیامک: {payload}")

    try:
        response = requests.post(url, json=payload)  # حتما json
        logging.info(f"🌐 وضعیت پاسخ HTTP: {response.status_code}")
        response.raise_for_status()

        data = response.json()
        logging.info(f"📨 پاسخ کامل API: {data}")

        if data.get("RetStatus") == 1:
            logging.info("✅ کد تایید با موفقیت ارسال شد.")
        else:
            logging.error(f"❌ خطا در ارسال کد: {data.get('StrRetStatus')}")

        return data
    except requests.exceptions.RequestException as e:
        logging.error(f"⚠️ خطای اتصال به ملی پیامک: {e}")
        return False
