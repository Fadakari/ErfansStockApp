import requests
import json
import os

# تنظیمات کلاینت بازار (اینو پر کن با اطلاعات خودت)
CLIENT_ID = "ClKPm20gjm5W5fcFeUsDoJN1OLXygo99ncHwqWeP"
CLIENT_SECRET = "xgUPf6NEGW8vu3jiG148bfKKjh7aQAuEmEsu88Aw3R1C9vzZu4EfD5yNa8WV"
REDIRECT_URI = "https://stockdivar.ir/dashboard"  # یا هر چی توی پنل دادی
AUTH_CODE = "cXn5Ops61XdOtvgUOBqPxzLCOuUq4b"
TOKEN_URL = "https://pardakht.cafebazaar.ir/devapi/v2/auth/token/"
TOKEN_FILE = "tokens.json"


def get_tokens_from_auth_code():
    data = {
        "grant_type": "authorization_code",
        "code": AUTH_CODE,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
    }

    response = requests.post(TOKEN_URL, data=data)
    print("Status Code:", response.status_code)
    print("Response:", response.text)

    if response.status_code == 200:
        tokens = response.json()
        with open(TOKEN_FILE, "w") as f:
            json.dump(tokens, f, indent=4)
        print("توکن‌ها ذخیره شدند در", TOKEN_FILE)
    else:
        print("خطا در دریافت توکن")


def refresh_access_token():
    if not os.path.exists(TOKEN_FILE):
        print("اول باید توکن اولیه رو بگیری (از کد).")
        return

    with open(TOKEN_FILE, "r") as f:
        tokens = json.load(f)

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print("refresh_token پیدا نشد!")
        return

    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
    }

    response = requests.post(TOKEN_URL, data=data)
    print("Status Code:", response.status_code)
    print("Response:", response.text)

    if response.status_code == 200:
        new_tokens = response.json()
        # refresh_token قدیمی رو حفظ می‌کنیم اگر جدید نیومد
        if "refresh_token" not in new_tokens:
            new_tokens["refresh_token"] = refresh_token

        with open(TOKEN_FILE, "w") as f:
            json.dump(new_tokens, f, indent=4)
        print("توکن جدید ذخیره شد.")
    else:
        print("خطا در رفرش کردن توکن")


if __name__ == "__main__":
    print("1. دریافت توکن از کد اولیه")
    print("2. رفرش توکن با استفاده از refresh_token")
    choice = input("عدد گزینه را وارد کنید: ")

    if choice == "1":
        get_tokens_from_auth_code()
    elif choice == "2":
        refresh_access_token()
    else:
        print("گزینه نامعتبر.")
