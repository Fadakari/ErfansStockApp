import os
from flask import render_template, redirect, url_for, flash, request, Blueprint, jsonify, session, url_for, current_app, abort, send_from_directory, request
from flask_login import login_user, logout_user, login_required, current_user
import secrets
import traceback
from urllib.parse import urlparse
from aplication import db
from models import User, Product, Category, EditProfileForm, Message, Conversation, Report, SignupTempData, ChatBotInteraction
from utils import save_image
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import logging
import random
import requests
from models import ProductType  # جایگزین yourapp با نام پروژه شما
from aplication import limiter
from sms_utils import send_verification_code
import re
import json
import urllib.parse
import base64
from flask_limiter.errors import RateLimitExceeded
from flask_limiter.util import get_remote_address
# from tensorflow.keras.applications.resnet50 import ResNet50, preprocess_input, decode_predictions
# from tensorflow.keras.preprocessing import image
# import numpy as np




logging.basicConfig(level=logging.DEBUG)
bp = Blueprint('main', __name__)

def custom_key():
    return f"{get_remote_address()}-{request.form.get('username', '')}"



# لیست استان‌ها و شهرهای مربوطه
@limiter.limit("5 per minute")
@bp.route('/')
def index():
    search = request.args.get('search', '').strip()
    province_search = request.args.get('province_search', '').strip()
    city_search = request.args.get('city_search', '').strip()
    category_id = request.args.get('category', '').strip()  # جستجو بر اساس دسته‌بندی
    address_search = request.args.get('address_search', '').strip()

    query = Product.query.filter(Product.status == 'published')

    # جستجو بر اساس نام محصول و توضیحات
    if search:
        search_filter = db.or_(
            Product.name.ilike(f'%{search}%'),
            Product.description.ilike(f'%{search}%')
        )
        query = query.filter(search_filter)

    # فیلتر بر اساس استان (استان در آدرس محصول باشد)
    if province_search:
        query = query.filter(Product.address.ilike(f'%{province_search}%'))

    # فیلتر بر اساس شهر (شهر در آدرس محصول باشد)
    if city_search:
        query = query.filter(Product.address.ilike(f'%{city_search}%'))

    # فیلتر بر اساس آدرس کامل
    if address_search:
        query = query.filter(Product.address.ilike(f'%{address_search}%'))

    # فیلتر بر اساس دسته‌بندی
    if category_id:
        query = query.filter(Product.category_id == category_id)

    # لیست استان‌های ایران
    provinces = [
        "آذربایجان شرقی", "آذربایجان غربی", "اردبیل", "اصفهان", "البرز", "ایلام", 
        "بوشهر", "تهران", "چهارمحال و بختیاری", "خراسان جنوبی", "خراسان رضوی", 
        "خراسان شمالی", "خوزستان", "زنجان", "سمنان", "سیستان و بلوچستان", "فارس", 
        "قزوین", "قم", "کردستان", "کرمان", "کرمانشاه", "کهگیلویه و بویراحمد", 
        "گلستان", "گیلان", "لرستان", "مازندران", "مرکزی", "هرمزگان", "همدان", "یزد"
    ]
    
    citiesByProvince = {
        "آذربایجان شرقی": ["تبریز", "اسکو", "اهر", "بستان‌آباد", "بناب", "جلفا", "چاراویماق", "خداآفرین", "سراب", "شبستر", "عجب‌شیر", "کلیبر", "مراغه", "مرند", "ملکان", "میانه", "ورزقان", "هریس", "هشترود"],
        "آذربایجان غربی": ["ارومیه", "اشنویه", "بوکان", "پلدشت", "پیرانشهر", "تکاب", "چالدران", "چایپاره", "خوی", "سردشت", "سلماس", "شاهین‌دژ", "شوط", "ماکو", "مهاباد", "میاندوآب", "نقده"],
        "اردبیل": ["اردبیل", "بیله‌سوار", "پارس‌آباد", "خلخال", "سرعین", "کوثر", "گرمی", "مشگین‌شهر", "نمین", "نیر"],
        "اصفهان": ["اصفهان", "آران و بیدگل", "اردستان", "برخوار", "بوئین و میاندشت", "تیران و کرون", "چادگان", "خمینی‌شهر", "خوانسار", "خور و بیابانک", "دهاقان", "سمیرم", "شاهین‌شهر و میمه", "شهرضا", "فریدن", "فریدون‌شهر", "فلاورجان", "کاشان", "گلپایگان", "لنجان", "مبارکه", "نائین", "نجف‌آباد", "نطنز"],
        "البرز": ["کرج", "اشتهارد", "ساوجبلاغ", "طالقان", "فردیس", "نظرآباد"],
        "ایلام": ["ایلام", "آبدانان", "ایوان", "بدره", "چرداول", "دره‌شهر", "دهلران", "سیروان", "ملکشاهی", "مهران"],
        "بوشهر": ["بوشهر", "تنگستان", "جم", "دشتستان", "دشتی", "دیر", "دیلم", "کنگان", "گناوه"],
        "تهران": ["تهران", "اسلامشهر", "بهارستان", "پاکدشت", "پردیس", "پیشوا", "دماوند", "رباط‌کریم", "ری", "شمیرانات", "شهریار", "فیروزکوه", "قدس", "قرچک", "ملارد", "ورامین"],
        "خراسان جنوبی": ["بیرجند", "بشرویه", "خوسف", "درمیان", "زیرکوه", "سرایان", "سربیشه", "طبس", "فردوس", "قائنات", "نهبندان"],
        "خراسان رضوی": ["مشهد", "بردسکن", "بجستان", "تایباد", "تربت جام", "تربت حیدریه", "چناران", "خلیل‌آباد", "خواف", "درگز", "رشتخوار", "زاوه", "سبزوار", "سرخس", "فریمان", "قوچان", "کاشمر", "کلات", "گناباد", "مه‌ولات", "نیشابور"],
        "خراسان شمالی": ["بجنورد", "اسفراین", "جاجرم", "راز و جرگلان", "شیروان", "فاروج", "گرمه", "مانه و سملقان"],
        "خوزستان": ["اهواز", "آبادان", "امیدیه", "اندیکا", "اندیمشک", "ایذه", "باغ‌ملک", "باوی", "بهبهان", "حمیدیه", "خرمشهر", "دزفول", "دشت آزادگان", "رامشیر", "رامهرمز", "شادگان", "شوش", "شوشتر", "کارون", "گتوند", "لالی", "ماهشهر", "مسجدسلیمان", "هفتکل", "هندیجان", "هویزه"],
        "فارس": ["شیراز", "آباده", "ارسنجان", "استهبان", "اقلید", "بوانات", "پاسارگاد", "جهرم", "خرامه", "خنج", "داراب", "زرین‌دشت", "سروستان", "سپیدان", "فسا", "فیروزآباد", "کازرون", "لارستان", "لامرد", "مرودشت", "ممسنی", "نی‌ریز"],
        "قزوین": ["قزوین", "آبیک", "البرز", "بوئین‌زهرا", "تاکستان", "آوج"],
        "قم": ["قم"],
        "کردستان": ["سنندج", "بانه", "بیجار", "دیواندره", "دهگلان", "سروآباد", "سقز", "قروه", "کامیاران", "مریوان"],
        "کرمان": ["کرمان", "ارزوئیه", "انار", "بافت", "بردسیر", "بم", "جیرفت", "رابر", "راور", "رودبار جنوب", "ریگان", "زرند", "سیرجان", "شهربابک", "عنبرآباد", "فاریاب", "فهرج", "قلعه گنج", "کوهبنان", "کهنوج", "منوجان"],
        "کرمانشاه": ["کرمانشاه", "اسلام‌آباد غرب", "پاوه", "ثلاث باباجانی", "جوانرود", "دالاهو", "روانسر", "سرپل ذهاب", "سنقر", "صحنه", "قصر شیرین", "کنگاور", "گیلانغرب", "هرسین"],
        "یزد": ["یزد", "ابرکوه", "اردکان", "اشکذر", "بافق", "بهاباد", "تفت", "خاتم", "مهریز", "میبد"]
    }

    # فقط شهرهایی که محصولی در آن‌ها وجود دارد را نمایش دهیم
    cities_with_products = []
    for province, cities in citiesByProvince.items():
        for city in cities:
            if Product.query.filter(Product.address.ilike(f'%{city}%')).first():
                cities_with_products.append(city)

    cities_with_products = list(set(cities_with_products))  # حذف شهرهای تکراری

    # دریافت محصولات پر بازدید (محصولاتی که بیشترین تعداد بازدید دارند)
    top_products = Product.query.order_by(Product.views.desc()).limit(3).all()

    # اگر تعداد محصولات کمتر از ۴ باشد، فقط پر بازدیدترین محصول را نمایش دهیم
    if len(top_products) < 4:
        top_products = top_products[:1]  # نمایش فقط یک محصول پر بازدید

    # مرتب‌سازی و دریافت محصولات
    products = query.order_by(
        db.case(
            (Product.promoted_until > datetime.utcnow(), 1),  # اگر نردبان شده، بالاتر قرار بگیرد
            else_=0  # در غیر این صورت، پایین‌تر قرار بگیرد
        ).desc(),  # ترتیب نزولی، یعنی نردبان‌شده‌ها بالاتر باشند
        Product.created_at.desc()  # سپس جدیدترین محصولات بالاتر باشند
    ).all()
    # دریافت دسته‌بندی‌ها
    categories = Category.query.filter_by(parent_id=None).all()
    return render_template('products.html', products=products, categories=categories, provinces=provinces,cities=cities_with_products, datetime=datetime, citiesByProvince=citiesByProvince, top_products=top_products)









@bp.route('/bazaar-login')
def bazaar_login():
    client_id = os.getenv('BAZAAR_CLIENT_ID')
    redirect_uri = 'https://stockdivar.ir/bazaar-callback'
    state = secrets.token_hex(16)

    # دیگه session نمی‌خوای اگر نمی‌خوای state چک کنی
    logging.warning("Generated state: %s", state)

    auth_url = (
        f"https://cafebazaar.ir/user/oauth?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"response_type=code&"
        f"state={state}"
    )

    return redirect(auth_url)


@bp.route('/bazaar-callback')
def bazaar_callback():
    logging.warning(">>> CALLBACK HIT <<<")

    code = request.args.get('code')
    state = request.args.get('state')
    logging.warning("Returned state: %s", state)

    # اگه نمی‌خوای چک کنی می‌تونی این بخش رو برداری:
    # if state != expected_state:
    #     flash("خطای امنیتی!", "danger")
    #     return redirect(url_for('main.login'))

    client_id = os.getenv('BAZAAR_CLIENT_ID')
    client_secret = os.getenv('BAZAAR_CLIENT_SECRET')
    redirect_uri = 'https://stockdivar.ir/bazaar-callback'

    # درخواست توکن
    token_url = "https://cafebazaar.ir/auth/token"
    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
        'client_id': client_id,
        'client_secret': client_secret
    }

    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.post(token_url, data=payload, headers=headers)
    logging.warning("Token response: %s", response.text)

    if response.status_code == 200:
        access_token = response.json()['access_token']

        user_info = get_bazaar_user_info(access_token)
        logging.warning("User info: %s", user_info)

        if user_info:
            phone = user_info.get('phone')
            flash(f"شماره موبایل بازار: {phone}", "success")
            return redirect(url_for('main.index'))

        flash("نتونستم اطلاعات کاربر رو بگیرم", "danger")
        return redirect(url_for('main.login'))

    flash("دریافت توکن از بازار ناموفق بود", "danger")
    return redirect(url_for('main.login'))



@bp.route('/bazaar-auth')
def bazaar_auth():
    return redirect(url_for('main.bazaar_login'))




def get_bazaar_user_info(access_token):
    try:
        res = requests.get(
            "https://cafebazaar.ir/auth/user",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        if res.status_code == 200:
            return res.json()
        return None
    except Exception as e:
        logging.error(f"خطا در دریافت اطلاعات کاربر از بازار: {e}")
        return None




def refresh_access_token(refresh_token):
    url = "https://cafebazaar.ir/tokens/refresh"
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }

    response = requests.post(url, data=data, headers=headers)
    if response.status_code == 200:
        return response.json()
    return None









@limiter.limit("5 per minute")
@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        identifier = request.form['username'].strip()

        # اول بررسی کن آیا این کاربر بلاک شده؟
        try:
            limiter.limit("5 per 2 minutes", key_func=custom_key)(lambda: None)()
        except RateLimitExceeded as e:
            reset_time = int(e.description.split(" ")[-1]) if "seconds" in e.description else 120
            flash(reset_time, "rate-limit-seconds")  # ارسال ثانیه‌ها برای JS
            flash(f"تلاش‌های بیش از حد! لطفاً {reset_time} ثانیه صبر کنید.", "rate-limit")  # پیام نمایشی
            return redirect(url_for('main.login'))

        password = request.form['password']

        user = User.query.filter(
            (User.username == identifier) | (User.phone == identifier)
        ).first()

        if user is None or not user.check_password(password):
            flash('نام کاربری یا رمز عبور نامعتبر است یا اکانت وجود ندارد', 'danger')
            return redirect(url_for('main.login'))

        # در صورت موفقیت
        whitelist_phones = ['09123456789']
        if user.phone in whitelist_phones:
            login_user(user, remember=True)
            flash('ورود با موفقیت انجام شد!', 'success')
            return redirect(url_for('main.index'))

        otp = random.randint(1000, 9999)
        session['otp_code'] = otp
        session['user_id'] = user.id
        send_verification_code(user.phone, otp)

        return redirect(url_for('main.verify_login'))

    return render_template('login.html')





@limiter.limit("5 per minute")
@bp.route('/verify_login', methods=['GET', 'POST'])
def verify_login():
    if request.method == 'POST':
        entered_code = request.form.get('code')
        user_id = session.get('user_id')
        otp_code = session.get('otp_code')

        if not user_id or not otp_code:
            flash('اطلاعات جلسه ناقص است. لطفاً دوباره وارد شوید.', 'danger')
            current_app.logger.warning("Session data missing during login verification.")
            return redirect(url_for('main.login'))

        user = User.query.get(user_id)

        if not user:
            flash('کاربر یافت نشد.', 'danger')
            current_app.logger.warning(f"No user found with ID {user_id}")
            return redirect(url_for('main.login'))

        # شماره‌های سفید که تاییدیه لازم ندارند:
        whitelist_phones = ['09123456789']  # این رو با شماره‌های موردنظر خودت عوض کن

        if user.phone in whitelist_phones:
            current_app.logger.info(f"User {user.phone} is in whitelist, bypassing OTP.")
        elif entered_code != str(otp_code):
            flash('کد وارد شده اشتباه است!', 'danger')
            current_app.logger.warning(f"Invalid OTP entered for user {user.phone}. Expected {otp_code}, got {entered_code}")
            return render_template('verify_login.html')

        # لاگین موفق
        login_user(user, remember=True)
        current_app.logger.info(f"User {user.phone} logged in successfully.")

        # پاک کردن سشن‌ها
        session.pop('otp_code', None)
        session.pop('user_id', None)

        flash('ورود با موفقیت انجام شد!', 'success')
        return redirect(url_for('main.index'))

    return render_template('verify_login.html')




@limiter.limit("5 per minute")
@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@bp.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    logging.debug("🏁 Dashboard function started")
    # دریافت محصولات کاربر
    products = Product.query.filter_by(user_id=current_user.id).all()
    
    # --- بررسی تاریخ انقضای محصولات (حذف محصولات منقضی‌شده) و نمایش هشدار تمدید برای محصولات نزدیک به انقضا ---
    now = datetime.utcnow()
    for product in products:
        logging.debug(f"📦 بررسی محصول: {product.name} | promoted_until: {product.promoted_until}")
        
        # محاسبه remaining_seconds برای تست سریع‌تر
        if product.promoted_until:
            remaining_seconds = int((product.promoted_until - now).total_seconds())
            product.remaining_seconds = remaining_seconds
            logging.debug(f"⏳ مانده تا انقضا (ثانیه): {remaining_seconds}")
        else:
            product.remaining_seconds = None
    
        if product.promoted_until and product.promoted_until < now:
            logging.debug(f"⏳ محصول منقضی شده: تغییر وضعیت به pending | {product.name}")
            product.status = 'pending'
            product.promoted_until = None
        elif product.promoted_until and (product.promoted_until - now) <= timedelta(seconds=30):
            logging.debug(f"⚠️ محصول نزدیک انقضا (کمتر از 30 ثانیه): {product.name}")
            product.near_expiration = True
        else:
            product.near_expiration = False

    # --- انتشار رایگان بعد از ۲۴ ساعت اگر تعداد محصولات در انتظار ≥ 5 باشد ---
    pending_products = [
        p for p in products 
        if p.status == 'pending' and (now - p.created_at) > timedelta(hours=24)
    ]

    free_publish_granted = False
    unpaid_product_ids = []

    for product in pending_products:
        product.status = 'published'
    
    if pending_products:
        db.session.commit()
        free_publish_granted = True
    else:
        unpaid_product_ids = [p.id for p in pending_products]

    # دریافت دسته‌بندی‌ها
    categories = Category.query.all()
    
    # فرم ویرایش پروفایل
    form = EditProfileForm(obj=current_user)
    if form.validate_on_submit():
        new_phone = form.phone.data.strip()
        if new_phone != current_user.phone:
            existing_user = User.query.filter_by(phone=new_phone).first()
            if existing_user:
                flash('این شماره تماس قبلاً ثبت شده است.', 'danger')
                return redirect(url_for('main.dashboard'))
            # شماره تغییر کرده => ارسال کد و هدایت به تأیید
            verification_code = str(random.randint(1000, 9999))
            session['phone_change_data'] = {
                'username': form.username.data,
                'email': form.email.data,
                'phone': new_phone
            }
            session['phone_change_code'] = verification_code
            send_verification_code(new_phone, f"کد تأیید تغییر شماره: {verification_code}")
            flash('کد تأیید به شماره جدید ارسال شد.', 'info')
            return redirect(url_for('main.verify_phone_change'))
        
        # شماره تغییر نکرده => ذخیره مستقیم
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        flash('اطلاعات شما با موفقیت بروزرسانی شد!')
        return redirect(url_for('main.dashboard'))
    # دریافت محصولات پر بازدید
    top_products = Product.query.order_by(Product.views.desc()).limit(3).all()
    if len(top_products) < 4:
        top_products = top_products[:1]

    # ارسال فرم ویرایش پروفایل
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        flash('اطلاعات شما با موفقیت بروزرسانی شد!')
        return redirect(url_for('main.dashboard'))

    can_promote = len(products) >= 5

    
    return render_template(
        'dashboard.html', 
        products=products, 
        categories=categories, 
        form=form, 
        top_products=top_products,
        free_publish_granted=free_publish_granted,
        unpaid_product_ids=unpaid_product_ids,
        can_promote=can_promote
    )

@bp.route('/verify-phone-change', methods=['GET', 'POST'])
@login_required
def verify_phone_change():
    data = session.get('phone_change_data')
    code = session.get('phone_change_code')

    if not data or not code:
        flash('داده‌ای برای تأیید موجود نیست.', 'danger')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        entered_code = request.form.get('code', '').strip()
        if entered_code == code:
            current_user.username = data['username']
            current_user.email = data['email']
            current_user.phone = data['phone']
            db.session.commit()

            session.pop('phone_change_data', None)
            session.pop('phone_change_code', None)

            flash('شماره تماس با موفقیت بروزرسانی شد.', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            flash('کد وارد شده اشتباه است.', 'danger')

    return render_template('verify_phone_change.html')


@bp.route('/renew_product/<int:product_id>', methods=['POST'])
@login_required
def renew_product(product_id):
    product = Product.query.filter_by(id=product_id, user_id=current_user.id).first_or_404()
    
    product.promoted_until = datetime.utcnow() + timedelta(days=30)
    product.status = 'published'
    
    db.session.commit()
    flash("محصول با موفقیت تمدید شد.", "success")
    return redirect(url_for('main.dashboard'))


@bp.route('/test/expire-soon')
@login_required
def test_expire_soon():
    from datetime import datetime, timedelta
    product = Product.query.filter_by(user_id=9, status='published').first()
    if product:
        product.promoted_until = datetime.utcnow() + timedelta(seconds=60)
        db.session.commit()
        return f"🔁 محصول «{product.name}» برای تست انقضا تنظیم شد (۶۰ ثانیه)"
    return "❌ هیچ محصولی با وضعیت published یافت نشد."



@limiter.limit("5 per minute")
@bp.route('/user-dashboard/<int:user_id>')
def user_dashboard(user_id):
    # بارگذاری اطلاعات کاربر بر اساس user_id
    user = User.query.get_or_404(user_id)
    
    # اگر کاربر وارد شده همان کاربر باشد یا ادمین باشد، محصولات آن کاربر را نشان بده
    if current_user.id == user.id or current_user.is_admin:
        # بارگذاری محصولات کاربر
        products = Product.query.filter_by(user_id=user.id).all()
        return render_template('user_dashboard.html', products=products, user=user)
    
    # اگر کاربر به داشبورد کاربر دیگری وارد شده و خودش ادمین نباشد
    flash("شما به این داشبورد دسترسی ندارید")
    return redirect(url_for('main.dashboard'))  # به صفحه اصلی هدایت می‌شود


@limiter.limit("5 per minute")
@bp.route('/product/new', methods=['GET', 'POST'])
@login_required
def new_product():
    if request.method == 'POST':
        try:
            # گرفتن داده‌ها از فرم
            name = request.form.get('name')
            description = request.form.get('description')
            price = request.form.get('price')
            category_id = request.form.get('category_id')
            product_type = request.form.get('product_type')
            province = request.form.get("province")
            city = request.form.get("city")
            address = f"{province}-{city}"
            postal_code = request.form.get("postal_code")
            brand = request.form.get('brand')

            # بررسی و ذخیره تصویر
            image_path = request.form.get('uploaded_image_path')

            # ایجاد و ذخیره محصول جدید در دیتابیس
            product = Product(
                name=name,
                description=description,
                price=price,
                image_path=image_path if image_path else None,
                user_id=current_user.id,
                category_id=category_id,
                address=address,
                postal_code=postal_code,
                product_type=ProductType[product_type] if product_type in ProductType.__members__ else None,
                brand=brand,
                status='pending'  # حالت پیش‌فرض برای بررسی توسط ادمین
            )

            db.session.add(product)
            db.session.commit()

            # تشخیص WebView
            user_agent = request.headers.get('User-Agent', '').lower()
            if 'wv' in user_agent or 'android' in user_agent:
                return render_template('upload_success.html')
            else:
                flash('محصول با موفقیت ایجاد شد و در انتظار تأیید است.', 'success')
                return redirect(url_for('main.dashboard'))

        except Exception as e:
            db.session.rollback()  # در صورت وقوع خطا تراکنش را لغو می‌کنیم
            logging.exception("خطا در ایجاد محصول:")
            flash('خطا در ایجاد محصول', 'danger')




    provinces = [
        "آذربایجان شرقی", "آذربایجان غربی", "اردبیل", "اصفهان", "البرز", "ایلام", 
        "بوشهر", "تهران", "چهارمحال و بختیاری", "خراسان جنوبی", "خراسان رضوی", 
        "خراسان شمالی", "خوزستان", "زنجان", "سمنان", "سیستان و بلوچستان", "فارس", 
        "قزوین", "قم", "کردستان", "کرمان", "کرمانشاه", "کهگیلویه و بویراحمد", 
        "گلستان", "گیلان", "لرستان", "مازندران", "مرکزی", "هرمزگان", "همدان", "یزد"
    ]

    citiesByProvince = {
        "آذربایجان شرقی": ["تبریز", "اسکو", "اهر", "بستان‌آباد", "بناب", "جلفا", "چاراویماق", "خداآفرین", "سراب", "شبستر", "عجب‌شیر", "کلیبر", "مراغه", "مرند", "ملکان", "میانه", "ورزقان", "هریس", "هشترود"],
        "آذربایجان غربی": ["ارومیه", "اشنویه", "بوکان", "پلدشت", "پیرانشهر", "تکاب", "چالدران", "چایپاره", "خوی", "سردشت", "سلماس", "شاهین‌دژ", "شوط", "ماکو", "مهاباد", "میاندوآب", "نقده"],
        "اردبیل": ["اردبیل", "بیله‌سوار", "پارس‌آباد", "خلخال", "سرعین", "کوثر", "گرمی", "مشگین‌شهر", "نمین", "نیر"],
        "اصفهان": ["اصفهان", "آران و بیدگل", "اردستان", "برخوار", "بوئین و میاندشت", "تیران و کرون", "چادگان", "خمینی‌شهر", "خوانسار", "خور و بیابانک", "دهاقان", "سمیرم", "شاهین‌شهر و میمه", "شهرضا", "فریدن", "فریدون‌شهر", "فلاورجان", "کاشان", "گلپایگان", "لنجان", "مبارکه", "نائین", "نجف‌آباد", "نطنز"],
        "البرز": ["کرج", "اشتهارد", "ساوجبلاغ", "طالقان", "فردیس", "نظرآباد"],
        "ایلام": ["ایلام", "آبدانان", "ایوان", "بدره", "چرداول", "دره‌شهر", "دهلران", "سیروان", "ملکشاهی", "مهران"],
        "بوشهر": ["بوشهر", "تنگستان", "جم", "دشتستان", "دشتی", "دیر", "دیلم", "کنگان", "گناوه"],
        "تهران": ["تهران", "اسلامشهر", "بهارستان", "پاکدشت", "پردیس", "پیشوا", "دماوند", "رباط‌کریم", "ری", "شمیرانات", "شهریار", "فیروزکوه", "قدس", "قرچک", "ملارد", "ورامین"],
        "خراسان جنوبی": ["بیرجند", "بشرویه", "خوسف", "درمیان", "زیرکوه", "سرایان", "سربیشه", "طبس", "فردوس", "قائنات", "نهبندان"],
        "خراسان رضوی": ["مشهد", "بردسکن", "بجستان", "تایباد", "تربت جام", "تربت حیدریه", "چناران", "خلیل‌آباد", "خواف", "درگز", "رشتخوار", "زاوه", "سبزوار", "سرخس", "فریمان", "قوچان", "کاشمر", "کلات", "گناباد", "مه‌ولات", "نیشابور"],
        "خراسان شمالی": ["بجنورد", "اسفراین", "جاجرم", "راز و جرگلان", "شیروان", "فاروج", "گرمه", "مانه و سملقان"],
        "خوزستان": ["اهواز", "آبادان", "امیدیه", "اندیکا", "اندیمشک", "ایذه", "باغ‌ملک", "باوی", "بهبهان", "حمیدیه", "خرمشهر", "دزفول", "دشت آزادگان", "رامشیر", "رامهرمز", "شادگان", "شوش", "شوشتر", "کارون", "گتوند", "لالی", "ماهشهر", "مسجدسلیمان", "هفتکل", "هندیجان", "هویزه"],
        "فارس": ["شیراز", "آباده", "ارسنجان", "استهبان", "اقلید", "بوانات", "پاسارگاد", "جهرم", "خرامه", "خنج", "داراب", "زرین‌دشت", "سروستان", "سپیدان", "فسا", "فیروزآباد", "کازرون", "لارستان", "لامرد", "مرودشت", "ممسنی", "نی‌ریز"],
        "قزوین": ["قزوین", "آبیک", "البرز", "بوئین‌زهرا", "تاکستان", "آوج"],
        "قم": ["قم"],
        "کردستان": ["سنندج", "بانه", "بیجار", "دیواندره", "دهگلان", "سروآباد", "سقز", "قروه", "کامیاران", "مریوان"],
        "کرمان": ["کرمان", "ارزوئیه", "انار", "بافت", "بردسیر", "بم", "جیرفت", "رابر", "راور", "رودبار جنوب", "ریگان", "زرند", "سیرجان", "شهربابک", "عنبرآباد", "فاریاب", "فهرج", "قلعه گنج", "کوهبنان", "کهنوج", "منوجان"],
        "کرمانشاه": ["کرمانشاه", "اسلام‌آباد غرب", "پاوه", "ثلاث باباجانی", "جوانرود", "دالاهو", "روانسر", "سرپل ذهاب", "سنقر", "صحنه", "قصر شیرین", "کنگاور", "گیلانغرب", "هرسین"],
        "یزد": ["یزد", "ابرکوه", "اردکان", "اشکذر", "بافق", "بهاباد", "تفت", "خاتم", "مهریز", "میبد"]
    }


    categories = Category.query.all()
    return render_template('product_form.html', categories=categories, provinces=provinces, citiesByProvince=citiesByProvince)



@bp.route('/upload-image', methods=['POST'])
@login_required
def upload_image():
    if 'image' not in request.files:
        return jsonify({'error': 'تصویری ارسال نشده'}), 400

    image = request.files['image']
    if image and image.filename:
        safe_filename = secure_filename(image.filename)
        image_path = save_image(image, safe_filename)
        return jsonify({'image_path': image_path}), 200

    return jsonify({'error': 'خطا در آپلود تصویر'}), 400


@bp.route('/admin/cleanup-images', methods=['POST'])
@login_required
def cleanup_images():
    if not current_user.is_admin:
        return jsonify({'error': 'دسترسی غیرمجاز'}), 403

    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
    all_files = set(os.listdir(upload_folder))
    used_files = set(os.path.basename(p.image_path) for p in Product.query.filter(Product.image_path != None).all())
    unused_files = all_files - used_files

    deleted = 0
    for filename in unused_files:
        try:
            os.remove(os.path.join(upload_folder, filename))
            deleted += 1
        except Exception as e:
            print(f"خطا در حذف {filename}: {e}")
    
    return jsonify({'message': f'{deleted} تصویر حذف شد'}), 200



@limiter.limit("5 per minute")
@bp.route('/product/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_product(id):
    product = Product.query.get_or_404(id)
    if product.user_id != current_user.id and not current_user.is_admin:
        flash('شما اجازه ویرایش این محصول را ندارید')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        try:
            product.name = request.form.get('name')
            product.description = request.form.get('description')
            product.category_id = request.form.get('category_id')
            product.price = float(request.form.get('price'))

            province = request.form.get("province")
            city = request.form.get("city")
            product.address = f"{province}-{city}"

            product.postal_code = request.form.get("postal_code")
            product.brand = request.form.get('brand')


            # دریافت و تبدیل product_type
            product_type = request.form.get("product_type")
            if product_type in ProductType.__members__:
                product.product_type = ProductType[product_type]
            else:
                product.product_type = None

            # بررسی آپلود تصویر جدید
            image = request.files.get('image')
            if image and image.filename:
                safe_filename = secure_filename(image.filename)
                new_image_path = save_image(image, safe_filename)
                if new_image_path:
                    # حذف تصویر قبلی
                    if product.image_path:
                        old_image_path = os.path.join('static/uploads', product.image_path)
                        if os.path.exists(old_image_path):
                            os.remove(old_image_path)
                    product.image_path = safe_filename  # اینجا تغییر

            db.session.commit()
            flash('محصول با موفقیت به‌روزرسانی شد')
            return redirect(url_for('main.dashboard'))

        except Exception as e:
            db.session.rollback()
            flash('خطا در به‌روزرسانی محصول', 'danger')

    provinces = [
        "آذربایجان شرقی", "آذربایجان غربی", "اردبیل", "اصفهان", "البرز", "ایلام", 
        "بوشهر", "تهران", "چهارمحال و بختیاری", "خراسان جنوبی", "خراسان رضوی", 
        "خراسان شمالی", "خوزستان", "زنجان", "سمنان", "سیستان و بلوچستان", "فارس", 
        "قزوین", "قم", "کردستان", "کرمان", "کرمانشاه", "کهگیلویه و بویراحمد", 
        "گلستان", "گیلان", "لرستان", "مازندران", "مرکزی", "هرمزگان", "همدان", "یزد"
    ]
    
    citiesByProvince = {
        "آذربایجان شرقی": ["تبریز", "اسکو", "اهر", "بستان‌آباد", "بناب", "جلفا", "چاراویماق", "خداآفرین", "سراب", "شبستر", "عجب‌شیر", "کلیبر", "مراغه", "مرند", "ملکان", "میانه", "ورزقان", "هریس", "هشترود"],
        "آذربایجان غربی": ["ارومیه", "اشنویه", "بوکان", "پلدشت", "پیرانشهر", "تکاب", "چالدران", "چایپاره", "خوی", "سردشت", "سلماس", "شاهین‌دژ", "شوط", "ماکو", "مهاباد", "میاندوآب", "نقده"],
        "اردبیل": ["اردبیل", "بیله‌سوار", "پارس‌آباد", "خلخال", "سرعین", "کوثر", "گرمی", "مشگین‌شهر", "نمین", "نیر"],
        "اصفهان": ["اصفهان", "آران و بیدگل", "اردستان", "برخوار", "بوئین و میاندشت", "تیران و کرون", "چادگان", "خمینی‌شهر", "خوانسار", "خور و بیابانک", "دهاقان", "سمیرم", "شاهین‌شهر و میمه", "شهرضا", "فریدن", "فریدون‌شهر", "فلاورجان", "کاشان", "گلپایگان", "لنجان", "مبارکه", "نائین", "نجف‌آباد", "نطنز"],
        "البرز": ["کرج", "اشتهارد", "ساوجبلاغ", "طالقان", "فردیس", "نظرآباد"],
        "ایلام": ["ایلام", "آبدانان", "ایوان", "بدره", "چرداول", "دره‌شهر", "دهلران", "سیروان", "ملکشاهی", "مهران"],
        "بوشهر": ["بوشهر", "تنگستان", "جم", "دشتستان", "دشتی", "دیر", "دیلم", "کنگان", "گناوه"],
        "تهران": ["تهران", "اسلامشهر", "بهارستان", "پاکدشت", "پردیس", "پیشوا", "دماوند", "رباط‌کریم", "ری", "شمیرانات", "شهریار", "فیروزکوه", "قدس", "قرچک", "ملارد", "ورامین"],
        "خراسان جنوبی": ["بیرجند", "بشرویه", "خوسف", "درمیان", "زیرکوه", "سرایان", "سربیشه", "طبس", "فردوس", "قائنات", "نهبندان"],
        "خراسان رضوی": ["مشهد", "بردسکن", "بجستان", "تایباد", "تربت جام", "تربت حیدریه", "چناران", "خلیل‌آباد", "خواف", "درگز", "رشتخوار", "زاوه", "سبزوار", "سرخس", "فریمان", "قوچان", "کاشمر", "کلات", "گناباد", "مه‌ولات", "نیشابور"],
        "خراسان شمالی": ["بجنورد", "اسفراین", "جاجرم", "راز و جرگلان", "شیروان", "فاروج", "گرمه", "مانه و سملقان"],
        "خوزستان": ["اهواز", "آبادان", "امیدیه", "اندیکا", "اندیمشک", "ایذه", "باغ‌ملک", "باوی", "بهبهان", "حمیدیه", "خرمشهر", "دزفول", "دشت آزادگان", "رامشیر", "رامهرمز", "شادگان", "شوش", "شوشتر", "کارون", "گتوند", "لالی", "ماهشهر", "مسجدسلیمان", "هفتکل", "هندیجان", "هویزه"],
        "فارس": ["شیراز", "آباده", "ارسنجان", "استهبان", "اقلید", "بوانات", "پاسارگاد", "جهرم", "خرامه", "خنج", "داراب", "زرین‌دشت", "سروستان", "سپیدان", "فسا", "فیروزآباد", "کازرون", "لارستان", "لامرد", "مرودشت", "ممسنی", "نی‌ریز"],
        "قزوین": ["قزوین", "آبیک", "البرز", "بوئین‌زهرا", "تاکستان", "آوج"],
        "قم": ["قم"],
        "کردستان": ["سنندج", "بانه", "بیجار", "دیواندره", "دهگلان", "سروآباد", "سقز", "قروه", "کامیاران", "مریوان"],
        "کرمان": ["کرمان", "ارزوئیه", "انار", "بافت", "بردسیر", "بم", "جیرفت", "رابر", "راور", "رودبار جنوب", "ریگان", "زرند", "سیرجان", "شهربابک", "عنبرآباد", "فاریاب", "فهرج", "قلعه گنج", "کوهبنان", "کهنوج", "منوجان"],
        "کرمانشاه": ["کرمانشاه", "اسلام‌آباد غرب", "پاوه", "ثلاث باباجانی", "جوانرود", "دالاهو", "روانسر", "سرپل ذهاب", "سنقر", "صحنه", "قصر شیرین", "کنگاور", "گیلانغرب", "هرسین"],
        "یزد": ["یزد", "ابرکوه", "اردکان", "اشکذر", "بافق", "بهاباد", "تفت", "خاتم", "مهریز", "میبد"]
    }

    # استخراج استان و شهر از مقدار ذخیره‌شده در دیتابیس
    product_province = product.address.split('-')[0] if product.address else ''
    product_city = product.address.split('-')[1] if '-' in product.address else ''

    categories = Category.query.all()
    return render_template('product_form.html', product=product, categories=categories, provinces=provinces, citiesByProvince=citiesByProvince, product_province=product_province, product_city=product_city)




@limiter.limit("5 per minute")
@bp.route('/product/<int:id>/delete', methods=['POST'])
@login_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    if product.user_id != current_user.id and not current_user.is_admin:
        flash('شما اجازه حذف این محصول را ندارید')
        return redirect(url_for('main.dashboard'))

    try:
        if product.image_path:
            image_path = os.path.join('static/uploads', product.image_path)
            if os.path.exists(image_path):
                os.remove(image_path)

        db.session.delete(product)
        db.session.commit()
        flash('محصول با موفقیت حذف شد')

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error deleting product: {str(e)}")
        flash('خطا در حذف محصول')

    return redirect(url_for('main.dashboard'))





@limiter.limit("5 per minute")
@bp.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    categories = Category.query.all()
    user = User.query.get(product.user_id)  # یا می‌توانید با استفاده از ارتباطات sqlalchemy این اطلاعات را بدست آورید
    phone = user.phone if user else None
    return render_template('product_detail.html', user=user, product=product, categories=categories, phone=phone)




@limiter.limit("5 per minute")
@bp.route('/init-categories')
def init_categories():
    categories = [
        {'name': 'ابزار کرگیری', 'icon': 'bi-drill', 'subcategories': [
            {'name': 'دریل', 'icon': 'bi-wrench'},
            {'name': 'فرز', 'icon': 'bi-gear'},
            {'name': 'کمپرسور', 'icon': 'bi-wind'}
        ]},
        {'name': 'ابزار اندازه گیری', 'icon': 'bi-rulers', 'subcategories': [
            {'name': 'اره برقی', 'icon': 'bi-tree'},
            {'name': 'چمن‌زن', 'icon': 'bi-flower3'}
        ]},
        {'name': 'مته و قلم', 'icon': 'bi-tools', 'subcategories': [
            {'name': 'جک هیدرولیک', 'icon': 'bi-car-front'},
            {'name': 'آچار بکس', 'icon': 'bi-wrench-adjustable'}
        ]},
        {'name': 'سیستم میخکوب ها', 'icon': 'bi-hammer', 'subcategories': []},
        {'name': 'ابزار برقی', 'icon': 'bi-lightning-charge', 'subcategories': []},
        {'name': 'ابزار شارژی', 'icon': 'bi-battery-full', 'subcategories': []},
    ]
    
    for cat in categories:
        parent = Category.query.filter_by(name=cat['name']).first()
        if not parent:
            parent = Category(name=cat['name'], icon=cat['icon'])
            db.session.add(parent)
        
        for subcat in cat['subcategories']:
            subcat_entry = Category.query.filter_by(name=subcat['name'], parent=parent).first()
            if not subcat_entry:
                subcat_entry = Category(name=subcat['name'], icon=subcat['icon'], parent=parent)
                db.session.add(subcat_entry)
    
    try:
        db.session.commit()
        flash('دسته‌بندی‌ها با موفقیت ایجاد شدند')
    except Exception as e:
        db.session.rollback()
        flash('خطا در ایجاد دسته‌بندی‌ها')
    
    return redirect(url_for('main.index'))







@limiter.limit("5 per minute")
@bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        def is_valid_phone(phone):
            return re.match(r'^09\d{9}$', phone)

        try:
            username = request.form.get('username')
            email = request.form.get('email')
            phone = request.form.get('phone')
            national_id = request.form.get('national_id')
            password = request.form.get('password')

            if not all([username, email, phone, national_id, password]):
                flash('لطفاً تمام فیلدها را پر کنید.', 'danger')
                return render_template('signup.html')

            if User.query.filter_by(username=username).first():
                flash('این نام کاربری قبلاً ثبت شده است.', 'danger')
                return render_template('signup.html')

            if User.query.filter_by(email=email).first():
                flash('این ایمیل قبلاً ثبت شده است.', 'danger')
                return render_template('signup.html')

            if User.query.filter_by(phone=phone).first():
                flash('این شماره تماس قبلاً ثبت شده است.', 'danger')
                return render_template('signup.html')

            if User.query.filter_by(national_id=national_id).first():
                flash('این کد ملی قبلاً ثبت شده است.', 'danger')
                return render_template('signup.html')

            if not is_valid_phone(phone):
                flash('شماره تماس نامعتبر است. باید با 09 شروع شده و 11 رقم باشد.', 'danger')
                return render_template('signup.html')

            verification_code = random.randint(1000, 9999)
            session['verification_code'] = str(verification_code)
            session['signup_data'] = {
                'username': username,
                'email': email,
                'phone': phone,
                'national_id': national_id,
                'password': password
            }

            # 🔥 فقط کد را ارسال می‌کنیم (نه متن آماده)
            print(f"📲 ارسال پیامک برای: {phone} با کد {verification_code}")
            send_verification_code(phone, str(verification_code))
            print('✅ ثبت نام موفق! هدایت به صفحه verify...')
            return redirect(url_for('main.verify'))

        except Exception as e:
            db.session.rollback()
            logging.error(f"Error in signup: {str(e)}")
            flash('خطا در ثبت‌نام. لطفاً دوباره تلاش کنید.', 'danger')
            return render_template('signup.html')

    return render_template('signup.html')



@bp.route('/verify', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def verify():
    admin_phones = ['09228192173']

    signup_data = session.get('signup_data')
    verification_code = str(session.get('verification_code', ''))

    if not signup_data or not verification_code:
        flash('خطای سیستمی! لطفاً دوباره ثبت‌نام کنید.', 'danger')
        return redirect(url_for('main.signup'))

    if request.method == 'POST':
        entered_code = request.form.get('code', '').strip()

        # اگر کاربر ادمین بود، جعل کد
        if signup_data.get('phone') in admin_phones:
            entered_code = verification_code

        if entered_code == verification_code:
            # ساخت حساب کاربری
            user = User(
                username=signup_data['username'],
                email=signup_data['email'],
                phone=signup_data['phone'],
                national_id=signup_data['national_id']
            )
            user.set_password(signup_data['password'])

            db.session.add(user)
            db.session.commit()

            # پاکسازی سشن
            session.pop('verification_code', None)
            session.pop('signup_data', None)

            flash('ثبت‌نام با موفقیت انجام شد.', 'success')
            return redirect(url_for('main.login'))
        else:
            flash('کد وارد شده اشتباه است!', 'danger')

    return render_template('verify.html')




@bp.route('/delete-uploaded-image', methods=['POST'])
@login_required
def delete_uploaded_image():
    data = request.get_json()
    image_path = data.get('image_path')

    if not image_path:
        return jsonify({'success': False, 'error': 'مسیر تصویر ارسال نشده'}), 400

    file_path = os.path.join(current_app.static_folder, 'uploads', image_path)
    if os.path.exists(file_path):
        os.remove(file_path)
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'فایل یافت نشد'}), 404




TOKENS_PATH = os.path.join(os.path.dirname(__file__), "tokens.json")

def get_valid_access_token():
    if os.path.exists(TOKENS_PATH):
        with open(TOKENS_PATH, "r") as f:
            tokens = json.load(f)
    else:
        tokens = {}

    access_token = tokens.get("access_token")
    expires_at = tokens.get("expires_at", 0)

    if not access_token or datetime.utcnow().timestamp() > expires_at:
        client_id = current_app.config["BAZAR_CLIENT_ID"].strip()
        client_secret = current_app.config["BAZAR_CLIENT_SECRET"].strip()

        token_url = "https://api.bazaarpay.ir/v1/oauth2/token"

        # ساخت هدر Authorization: Basic base64(client_id:client_secret)
        basic_auth_str = f"{client_id}:{client_secret}"
        basic_auth_bytes = basic_auth_str.encode("utf-8")
        basic_auth_b64 = base64.b64encode(basic_auth_bytes).decode("utf-8")
        headers = {
            "Authorization": f"Basic {basic_auth_b64}",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        # پارامترهای فرم برای grant_type=client_credentials
        data = {
            "grant_type": "client_credentials"
        }

        res = requests.post(token_url, headers=headers, data=data)
        res.raise_for_status()
        token_data = res.json()

        access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in", 3600)

        tokens = {
            "access_token": access_token,
            "expires_at": (datetime.utcnow() + timedelta(seconds=expires_in - 60)).timestamp()
        }
        with open(TOKENS_PATH, "w") as f:
            json.dump(tokens, f)

    return access_token


@bp.route("/payment/start/<int:product_id>", methods=["GET"])
@login_required
def start_payment(product_id):
    current_app.logger.debug(f"🔄 Start payment route called with product_id={product_id}")

    product = Product.query.get_or_404(product_id)
    current_app.logger.debug(f"📦 Product found: {product.name}")

    amount_toman = 30000
    callback_url = url_for("main.payment_callback", _external=True) + f"?product_id={product.id}&pay_type=promote"

    try:
        access_token = get_valid_access_token()
        if not access_token:
            flash("دریافت توکن بازارپی ناموفق بود.", "danger")
            return redirect(url_for("main.dashboard"))

        payment_url = "https://api.bazaarpay.ir/v1/payments/direct-payments"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        payment_data = {
            "amount": amount_toman,
            "callback_url": callback_url,
            "description": f"پرداخت برای نردبان کردن محصول {product.name}",
            "payer_id": str(current_user.id)
        }

        current_app.logger.debug(f"💳 Creating payment with data: {payment_data}")
        payment_res = requests.post(payment_url, headers=headers, json=payment_data)
        payment_res.raise_for_status()

        payment_result = payment_res.json()
        current_app.logger.debug(f"💬 Payment response: {payment_result}")

        payment_url = payment_result.get("payment_url")
        if payment_url:
            return redirect(payment_url)
        else:
            flash("خطا در ساخت پرداخت با بازارپی!", "danger")
            return redirect(url_for("main.dashboard"))

    except requests.RequestException as e:
        current_app.logger.error(f"❌ خطا در اتصال به بازارپی: {e}")
        flash("مشکلی در اتصال به بازارپی رخ داد.", "danger")
        return redirect(url_for("main.dashboard"))


@bp.route("/payment/callback", methods=["GET", "POST"])
def payment_callback():
    data = request.args if request.method == "GET" else request.form

    ref_id = data.get("ref_id")
    product_id = data.get("product_id")
    pay_type = data.get("pay_type")

    if not ref_id or not product_id or not pay_type:
        flash("اطلاعات بازگشتی ناقص است.", "danger")
        return redirect(url_for("main.index"))

    try:
        product_id = int(product_id)
    except ValueError:
        flash("شناسه محصول نامعتبر است.", "danger")
        return redirect(url_for("main.index"))

    product = Product.query.get(product_id)
    if not product:
        flash("محصول یافت نشد.", "danger")
        return redirect(url_for("main.index"))

    try:
        access_token = get_valid_access_token()
        if not access_token:
            flash("دریافت توکن بازارپی ناموفق بود.", "danger")
            return redirect(url_for("main.index"))

        verify_url = "https://api.bazaarpay.ir/v1/payments/verify"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        verify_res = requests.post(verify_url, headers=headers, json={"ref_id": ref_id})
        verify_res.raise_for_status()
        verify_data = verify_res.json()

        if verify_data.get("verified"):
            now = datetime.utcnow()
            if pay_type == "promote":
                product.promoted_until = now + timedelta(days=10)
                db.session.commit()
                flash("محصول با موفقیت نردبان شد!", "success")
            else:
                flash("نوع پرداخت نامعتبر است.", "danger")
        else:
            flash("پرداخت ناموفق بود یا تایید نشد.", "danger")

    except requests.RequestException as e:
        current_app.logger.error(f"خطا در تایید پرداخت بازارپی: {e}")
        flash("خطا در تایید پرداخت بازارپی.", "danger")

    return redirect(url_for("main.dashboard"))




@limiter.limit("5 per minute")
@bp.route("/product/<int:product_id>/remove-promotion", methods=["POST"])
@login_required
def remove_promotion(product_id):
    """حذف نردبان محصول به صورت دستی"""
    product = Product.query.get_or_404(product_id)
    
    # بررسی اینکه فقط صاحب محصول یا ادمین می‌توانند نردبان را حذف کنند
    if product.user_id != current_user.id and not current_user.is_admin:
        flash('شما اجازه حذف نردبان این محصول را ندارید')
        return redirect(url_for('main.dashboard'))

    # تنظیم promoted_until به None برای برداشتن نردبان
    product.promoted_until = None
    db.session.commit()

    flash('نردبان محصول با موفقیت برداشته شد!')
    return redirect(url_for('main.dashboard'))




@limiter.limit("5 per minute")
@bp.route("/product/<int:product_id>/promote", methods=["POST"])
@login_required
def promote_product(product_id):
    """نردبان کردن محصول به صورت دستی"""
    product = Product.query.get_or_404(product_id)

    # فقط صاحب محصول یا ادمین می‌توانند محصول را نردبان کنند
    if product.user_id != current_user.id and not current_user.is_admin:
        flash('شما اجازه نردبان کردن این محصول را ندارید')
        return redirect(url_for('main.dashboard'))

    # تنظیم promoted_until برای 10 ثانیه بعد از زمان فعلی
    product.promoted_until = datetime.utcnow() + timedelta(days=10)
    db.session.commit()

    flash('محصول به مدت 10 روز نردبان شد!')
    return redirect(url_for('main.dashboard'))



@limiter.limit("5 per minute")
@bp.route("/admin", methods=["GET"])
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash("شما دسترسی به این بخش را ندارید", "danger")
        return redirect(url_for('main.index'))
    
    query = request.args.get('query', '').strip()  # دریافت مقدار جست‌وجو
    role_filter = request.args.get('role_filter', '')  # دریافت فیلتر نقش (ادمین یا کاربر عادی)
    pending_products = Product.query.filter_by(status='pending').all()
    users_dict = {u.id: u.username for u in User.query.all()}

    # دریافت تمام کاربران
    users = User.query

    # جست‌وجو بر اساس نام کاربری، ایمیل، شماره تماس و کد ملی
    if query:
        users = users.filter(
            (User.username.ilike(f"%{query}%")) | 
            (User.email.ilike(f"%{query}%")) | 
            (User.phone.ilike(f"%{query}%")) | 
            (User.national_id.ilike(f"%{query}%"))
        )

    # فیلتر بر اساس نقش (ادمین یا کاربر عادی)
    if role_filter == "admin":
        users = users.filter(User.is_admin == True)
    elif role_filter == "user":
        users = users.filter(User.is_admin == False)

    users = users.all()  # اجرای کوئری

    # دریافت تمام دسته‌بندی‌ها
    categories = Category.query.all()
    reports = Report.query.order_by(Report.created_at.desc()).all()

    return render_template("admin_dashboard.html", users=users, categories=categories, reports=reports, pending_products=pending_products, users_dict=users_dict)



@bp.route("/admin/approve_product/<int:product_id>", methods=["POST"])
@login_required
def approve_product(product_id):
    if not current_user.is_admin:
        flash("شما دسترسی ندارید", "danger")
        return redirect(url_for("main.index"))

    product = Product.query.get_or_404(product_id)
    product.status = "published"
    db.session.commit()

    flash("محصول با موفقیت تأیید شد", "success")
    return redirect(url_for("main.admin_dashboard"))



@bp.route('/report_violation/<int:product_id>', methods=['POST'])
@login_required
def report_violation(product_id):
    report_text = request.form.get('report_text')
    if report_text:
        report = Report(product_id=product_id, reporter_id=current_user.id, text=report_text)
        db.session.add(report)
        db.session.commit()
        flash('گزارش شما با موفقیت ثبت شد.', 'success')
    else:
        flash('متن گزارش نمی‌تواند خالی باشد.', 'danger')
    return redirect(url_for('main.product_detail', product_id=product_id))


@bp.route('/admin/delete_report/<int:report_id>', methods=['POST'])
@login_required
def delete_report(report_id):
    if not current_user.is_admin:
        flash("شما دسترسی به این بخش را ندارید", "danger")
        return redirect(url_for('main.index'))

    report = Report.query.get_or_404(report_id)
    db.session.delete(report)
    db.session.commit()
    flash("گزارش با موفقیت حذف شد.", "success")
    return redirect(url_for('main.admin_dashboard'))




@limiter.limit("5 per minute")
@bp.route("/make_admin/<int:user_id>", methods=["POST"])
@login_required
def make_admin(user_id):
    if not current_user.is_admin:
        flash("شما دسترسی لازم برای این کار را ندارید")
        return redirect(url_for('main.admin_dashboard'))
    
    user = User.query.get_or_404(user_id)
    user.is_admin = True  # تبدیل کاربر به ادمین
    db.session.commit()

    flash("کاربر با موفقیت به ادمین تبدیل شد")
    return redirect(url_for('main.admin_dashboard'))


@limiter.limit("5 per minute")
@bp.route("/remove_admin/<int:user_id>", methods=["POST"])
@login_required
def remove_admin(user_id):
    if not current_user.is_admin:
        flash("شما دسترسی لازم برای این کار را ندارید")
        return redirect(url_for('main.admin_dashboard'))
    
    user = User.query.get_or_404(user_id)
    user.is_admin = False  # حذف نقش ادمین از کاربر
    db.session.commit()

    flash("کاربر با موفقیت از ادمین بودن حذف شد")
    return redirect(url_for('main.admin_dashboard'))




@limiter.limit("5 per minute")
@bp.route("/add-category", methods=["POST"])
@login_required
def add_category():
    if not current_user.is_admin:
        flash("شما دسترسی لازم برای این کار را ندارید")
        return redirect(url_for('main.index'))

    category_name = request.form.get('category_name')
    if category_name:
        category = Category(name=category_name)
        db.session.add(category)
        db.session.commit()
        flash("دسته‌بندی جدید با موفقیت اضافه شد")
    else:
        flash("نام دسته‌بندی وارد نشده است")

    return redirect(url_for('main.admin_dashboard'))


@limiter.limit("5 per minute")
@bp.route("/delete_user/<int:user_id>", methods=["POST"])
@login_required
def delete_user(user_id):
    """حذف کاربر توسط ادمین اصلی"""
    if not current_user.is_admin:
        flash("شما دسترسی لازم برای این کار را ندارید")
        return redirect(url_for('main.admin_dashboard'))

    user = User.query.get_or_404(user_id)

    # جلوگیری از حذف ادمین اصلی
    if user.is_admin and user.id == current_user.id:
        flash("نمی‌توانید ادمین اصلی را حذف کنید!")
        return redirect(url_for('main.admin_dashboard'))

    db.session.delete(user)
    db.session.commit()
    
    flash(f"کاربر '{user.username}' با موفقیت حذف شد")
    return redirect(url_for('main.admin_dashboard'))


@limiter.limit("5 per minute")
@bp.route("/delete_category/<int:category_id>", methods=["POST"])
@login_required
def delete_category(category_id):
    """حذف دسته‌بندی توسط ادمین"""
    if not current_user.is_admin:
        flash("شما دسترسی لازم برای این کار را ندارید")
        return redirect(url_for('main.admin_dashboard'))

    category = Category.query.get_or_404(category_id)

    # بررسی اینکه آیا محصولی در این دسته‌بندی وجود دارد
    if category.products:
        flash("نمی‌توانید دسته‌بندی‌ای که دارای محصول است را حذف کنید!")
        return redirect(url_for('main.admin_dashboard'))

    db.session.delete(category)
    db.session.commit()

    flash(f"دسته‌بندی '{category.name}' با موفقیت حذف شد")
    return redirect(url_for('main.admin_dashboard'))




@limiter.limit("5 per minute")  
@bp.route("/fake-payment", methods=["POST"])
def fake_payment():
    """شبیه‌سازی درگاه پرداخت زیبال بدون نیاز به درگاه واقعی"""
    track_id = "123456789"  # مقدار فیک برای تست
    return jsonify({"result": 100, "trackId": track_id})


    return render_template('signup.html')





@bp.route('/pay-to-publish/<int:product_id>', methods=['POST'])
def pay_to_publish(product_id):
    product = Product.query.get_or_404(product_id)
    if product.status == 'awaiting_payment':
        # اینجا باید به درگاه پرداخت وصل بشی. فرض کنیم پرداخت موفقه.
        product.status = 'published'
        db.session.commit()
        flash('محصول شما با موفقیت منتشر شد!', 'success')
    return redirect(url_for('main.dashboard'))


@bp.route('/ionicApp-server')
def serve_ionic_app():
    ionic_build_path = '/var/www/ionic-app'
    return send_from_directory(ionic_build_path, 'index.html')

@bp.route('/ionicApp-server/<path:path>')
def serve_ionic_static(path):
    ionic_build_path = '/var/www/ionic-app'
    return send_from_directory(ionic_build_path, path)



@bp.route("/conversations")
@login_required
def conversations():
    convos = Conversation.query.filter(
        (Conversation.user1_id == current_user.id) | (Conversation.user2_id == current_user.id)
    ).all()
    return render_template("conversations.html", conversations=convos)

@bp.route("/conversation/<int:conversation_id>", methods=["GET", "POST"])
@login_required
def conversation(conversation_id):
    convo = Conversation.query.get_or_404(conversation_id)

    # بررسی دسترسی کاربر
    if current_user.id not in [convo.user1_id, convo.user2_id]:
        return "Unauthorized", 403

    if request.method == "POST":
        content = request.form.get("content", "").strip()
        file = request.files.get("file")
        filename = None

        # اگر فایلی انتخاب شده بود، ذخیره‌اش می‌کنیم
        if file and file.filename:
            filename = secure_filename(file.filename)
            file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
            file.save(file_path)

        receiver_id = convo.user2_id if current_user.id == convo.user1_id else convo.user1_id

        new_msg = Message(
            sender_id=current_user.id,
            receiver_id=receiver_id,
            content=content,
            conversation_id=conversation_id,
            file_path=filename  # فیلد جدید مدل Message
        )
        db.session.add(new_msg)
        db.session.commit()

        return redirect(url_for("main.conversation", conversation_id=conversation_id))

    messages = Message.query.filter_by(conversation_id=conversation_id).order_by(Message.timestamp.asc()).all()
    return render_template("chat.html", conversation=convo, messages=messages)



@bp.route("/start_conversation/<int:user_id>")
@login_required
def start_conversation(user_id):
    # جلوگیری از چت با خود
    if current_user.id == user_id:
        return redirect(url_for("index"))

    existing = Conversation.query.filter(
        ((Conversation.user1_id == current_user.id) & (Conversation.user2_id == user_id)) |
        ((Conversation.user1_id == user_id) & (Conversation.user2_id == current_user.id))
    ).first()

    if existing:
        return redirect(url_for("main.conversation", conversation_id=existing.id))

    # ایجاد مکالمه جدید
    new_convo = Conversation(user1_id=current_user.id, user2_id=user_id)
    db.session.add(new_convo)
    db.session.commit()

    return redirect(url_for("main.conversation", conversation_id=new_convo.id))



@bp.route('/delete_message/<int:message_id>', methods=['POST'])
@login_required
def delete_message(message_id):
    msg = Message.query.get_or_404(message_id)
    if msg.sender_id != current_user.id:
        abort(403)
    conversation_id = msg.conversation_id
    db.session.delete(msg)
    db.session.commit()
    return redirect(url_for('main.conversation', conversation_id=conversation_id))

@bp.route('/edit_message_inline/<int:message_id>', methods=['POST'])
@login_required
def edit_message_inline(message_id):
    msg = Message.query.get_or_404(message_id)
    if msg.sender_id != current_user.id:
        abort(403)
    new_content = request.form.get('content')
    if new_content:
        msg.content = new_content
        db.session.commit()
    return redirect(url_for('main.conversation', conversation_id=msg.conversation_id))




@bp.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@bp.route("/privacy")
def privacy():
    return render_template("security.html")


@bp.route('/chatbot', methods=['GET', 'POST'])
@login_required
def chatbot_page():
    bot_response = None
    products_info = []

    if request.method == 'POST':
        user_query = request.form.get('query')
        if not user_query:
            flash('سؤال نمی‌تواند خالی باشد.', 'warning')
            return redirect(url_for('main.chatbot_page'))

        # فراخوانی DeepSeek API
        try:
            response = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {current_app.config['DEEPSEEK_API_KEY']}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": user_query}],
                    "max_tokens": 1000
                }
            )

            # بررسی وضعیت پاسخ و استخراج محتوا
            if response.status_code == 200:
                data = response.json()
                # بررسی وجود کلید choices
                if "choices" in data and len(data["choices"]) > 0:
                    bot_response = data["choices"][0]["message"]["content"]
                else:
                    bot_response = "پاسخی از ربات دریافت نشد."
            else:
                bot_response = f"خطا در درخواست API: {response.status_code}"

        except Exception as e:
            flash(f'خطا در تماس با API: {str(e)}', 'danger')
            return redirect(url_for('main.chatbot_page'))

        # ذخیره تعامل
        interaction = ChatBotInteraction(
            user_id=current_user.id,
            user_query=user_query,
            bot_response=bot_response
        )
        db.session.add(interaction)
        db.session.commit()

        # پیدا کردن محصولات مرتبط
        related_products = find_related_products(user_query)
        if related_products:
            interaction.products_related = ",".join(str(p.id) for p in related_products)
            db.session.commit()

            products_info = [{
                'id': p.id,
                'name': p.name,
                'price': p.price,
                'image': url_for('main.uploaded_file', filename=p.image_path) if p.image_path else None
            } for p in related_products]

    return render_template('ai_chat.html', bot_response=bot_response, products=products_info)


def find_related_products(query):
    # تجزیه و تحلیل کوئری کاربر
    keywords = query.lower().split()

    # جستجوی محصولات بر اساس کلمات کلیدی
    products = Product.query.filter(
        db.or_(
            *[Product.name.ilike(f'%{kw}%') for kw in keywords],
            *[Product.description.ilike(f'%{kw}%') for kw in keywords]
        )
    ).limit(5).all()

    return products




# def classify_image(img_path):
#     img = image.load_img(img_path, target_size=(224, 224))
#     x = image.img_to_array(img)
#     x = np.expand_dims(x, axis=0)
#     x = preprocess_input(x)

#     preds = model.predict(x)
#     decoded = decode_predictions(preds, top=3)[0]
#     return decoded


# @bp.route('/analyze-uploaded-image', methods=['POST'])
# @login_required
# def analyze_uploaded_image():
#     if 'image' not in request.files:
#         return jsonify({'error': 'تصویری ارسال نشده'}), 400

#     image_file = request.files['image']
#     if image_file and image_file.filename:
#         safe_filename = secure_filename(image_file.filename)
#         image_path = save_image(image_file, safe_filename)

#         try:
#             predictions = classify_image(image_path)
#             results = [{'label': p[1], 'confidence': float(p[2])} for p in predictions]
#             return jsonify({'image_path': image_path, 'predictions': results}), 200
#         except Exception as e:
#             return jsonify({'error': f'خطا در پردازش تصویر: {str(e)}'}), 500

#     return jsonify({'error': 'خطا در آپلود تصویر'}), 400


# در تابع chatbot بعد از دریافت پاسخ از API:
# related_products = find_related_products(user_query)
# if related_products:
#     product_ids = ",".join(str(p.id) for p in related_products)
#     interaction.products_related = product_ids
#     db.session.commit()
    
#     # اضافه کردن اطلاعات محصولات به پاسخ
#     products_info = [{
#         'id': p.id,
#         'name': p.name,
#         'price': p.price,
#         'image': url_for('main.uploaded_file', filename=p.image_path) if p.image_path else None
#     } for p in related_products]
    
#     return jsonify({
#         'response': bot_response,
#         'products': products_info
#     })


# @bp.route('/conversations')
# @login_required
# def conversations():
#     convs = Conversation.query.filter(
#         (Conversation.user1_id == current_user.id) | 
#         (Conversation.user2_id == current_user.id)
#     ).all()
#     return render_template('conversations.html', conversations=convs)


# @bp.route('/chat/<int:user_id>', methods=['GET', 'POST'])
# @login_required
# def chat(user_id):
#     user = User.query.get_or_404(user_id)
    
#     if request.method == 'POST':
#         content = request.form.get('content')
#         replied_to_id = request.form.get('replied_to_id')

#         if content:
#             convo = Conversation.query.filter(
#                 ((Conversation.user1_id == current_user.id) & (Conversation.user2_id == user_id)) |
#                 ((Conversation.user1_id == user_id) & (Conversation.user2_id == current_user.id))
#             ).first()

#             if not convo:
#                 convo = Conversation(user1_id=current_user.id, user2_id=user_id)
#                 db.session.add(convo)
#                 db.session.commit()

#             msg = Message(
#                 sender_id=current_user.id,
#                 conversation_id=convo.id,
#                 content=content,
#                 replied_to_id=replied_to_id if replied_to_id else None
#             )
#             db.session.add(msg)
#             db.session.commit()

#             # هدایت به همان صفحه پس از ارسال پیام
#             return redirect(url_for('main.chat', user_id=user.id))
    
#     # برای متد GET پیام‌ها را بارگذاری می‌کنیم
#     messages = Message.query.filter(
#         (Message.sender_id == current_user.id) | 
#         (Message.receiver_id == current_user.id)
#     ).order_by(Message.timestamp).all()

#     convo = Conversation.query.filter(
#         ((Conversation.user1_id == current_user.id) & (Conversation.user2_id == user_id)) |
#         ((Conversation.user1_id == user_id) & (Conversation.user2_id == current_user.id))
#     ).first()

#     return render_template('chat.html', user=user, messages=messages)








# @bp.route('/edit_message/<int:message_id>', methods=['POST'])
# @login_required
# def edit_message(message_id):
#     msg = Message.query.get_or_404(message_id)
#     if msg.sender_id != current_user.id:
#         return jsonify(success=False), 403
#     data = request.get_json()
#     msg.content = data.get('content', '').strip()
#     db.session.commit()
#     return jsonify(success=True)

# @bp.route('/delete_message/<int:message_id>', methods=['POST'])
# @login_required
# def delete_message(message_id):
#     msg = Message.query.get_or_404(message_id)
#     if msg.sender_id != current_user.id:
#         return jsonify(success=False), 403
#     db.session.delete(msg)
#     db.session.commit()
#     return jsonify(success=True)




# def get_conversation_id(user_id):
#     # پیدا کردن مکالمه‌ای که کاربر در آن حضور دارد
#     conversation = Conversation.query.filter(
#         (Conversation.user1_id == user_id) | 
#         (Conversation.user2_id == user_id)
#     ).first()  # پیدا کردن اولین مکالمه که کاربر در آن حضور دارد
    
#     if conversation:
#         return conversation.id
#     else:
#         # اگر مکالمه‌ای پیدا نشد، مکالمه جدید ایجاد می‌کنیم
#         new_conversation = Conversation(user1_id=user_id, user2_id=user_id)  # مثال: فرض می‌کنیم هر دو کاربر یکسان‌اند
#         db.session.add(new_conversation)
#         db.session.commit()
#         return new_conversation.id

# @bp.route('/send_message', methods=['POST'])
# def send_message():
#     try:
#         content = request.form['content']
#         replied_to_id = request.form.get('replied_to_id')

#         # برای پیدا کردن conversation_id
#         conversation_id = get_conversation_id(current_user.id)

#         # ذخیره پیام جدید در دیتابیس
#         new_message = Message(content=content, sender_id=current_user.id, replied_to_id=replied_to_id, conversation_id=conversation_id)
#         db.session.add(new_message)
#         db.session.commit()

#         # بازیابی تمامی پیام‌ها برای این گفتگو
#         messages = Message.query.filter_by(conversation_id=conversation_id).all()

#         # تبدیل پیام‌ها به فرمت JSON برای ارسال به کلاینت
#         message_data = []
#         for msg in messages:
#             message_data.append({
#                 'id': msg.id,
#                 'content': msg.content,
#                 'sender': msg.sender.username,
#                 'replied_to': msg.replied_to.content if msg.replied_to else None
#             })

#         return jsonify({'success': True, 'messages': message_data})

#     except Exception as e:
#         # در صورت بروز خطا، پیام خطا ارسال می‌کنیم
#         return jsonify({'success': False, 'error': str(e)}), 500
    

# # روت دیگر (مثال) که پیام‌ها را برای نمایش به کلاینت می‌آورد
# @bp.route('/get_messages')
# def get_messages():
#     conversation_id = get_conversation_id(current_user.id)
#     messages = Message.query.filter_by(conversation_id=conversation_id).all()
    
#     message_data = []
#     for msg in messages:
#         message_data.append({
#             'id': msg.id,
#             'content': msg.content,
#             'sender': msg.sender.username,
#             'replied_to': msg.replied_to.content if msg.replied_to else None
#         })

#     return jsonify({'messages': message_data})


@bp.route('/api/products')
def api_products():
    search = request.args.get('search', '').strip()
    province_search = request.args.get('province_search', '').strip()
    city_search = request.args.get('city_search', '').strip()
    category_id = request.args.get('category', '').strip()
    address_search = request.args.get('address_search', '').strip()

    query = Product.query.filter(Product.status == 'published')

    if search:
        query = query.filter(
            db.or_(
                Product.name.ilike(f'%{search}%'),
                Product.description.ilike(f'%{search}%')
            )
        )

    if province_search:
        query = query.filter(Product.address.ilike(f'%{province_search}%'))

    if city_search:
        query = query.filter(Product.address.ilike(f'%{city_search}%'))

    if address_search:
        query = query.filter(Product.address.ilike(f'%{address_search}%'))

    if category_id:
        query = query.filter(Product.category_id == category_id)

    products = query.order_by(
        db.case(
            (Product.promoted_until > datetime.utcnow(), 1),
            else_=0
        ).desc(),
        Product.created_at.desc()
    ).all()

    # تبدیل به JSON
    def serialize_product(product):
        return {
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "address": product.address,
            "views": product.views,
            "created_at": product.created_at.isoformat(),
            "promoted_until": product.promoted_until.isoformat() if product.promoted_until else None,
            "category_id": product.category_id,
            "image_url": f"https://stockdivar.ir/static/uploads/{product.image_path}" if product.image_path else None
        }

    return jsonify({
        "products": [serialize_product(p) for p in products]
    })

@bp.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory('/var/www/myproject2/static/uploads', filename)


@bp.route('/api/product/<int:product_id>')
@limiter.limit("5 per minute")
def api_product_detail(product_id):
    try:
        product = Product.query.get_or_404(product_id)
        user = User.query.get(product.user_id)
        category = Category.query.get(product.category_id)

        return jsonify({
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "price": product.price,
            "address": product.address,
            "postal_code": product.postal_code,
            "views": product.views,
            "created_at": product.created_at.isoformat() if product.created_at else None,
            "promoted_until": product.promoted_until.isoformat() if product.promoted_until else None,
            "status": product.status,
            "product_type": str(product.product_type) if product.product_type else None,
            "category": category.name if category else None,
            "user": {
                "id": user.id,
                "phone": user.phone
            } if user else None,
            "image_url": url_for('main.uploaded_file', filename=product.image_path, _external=True)
        })
    
    except Exception as e:
        print(f"Error in api_product_detail: {e}")
        traceback.print_exc()
        return jsonify({"error": "Internal server error"}), 500


@bp.route('/api/report_violation/<int:product_id>', methods=['POST'])
@login_required
def api_report_violation(product_id):
    data = request.get_json()
    report_text = data.get('report_text') if data else None

    if not report_text:
        return jsonify({"error": "متن گزارش نمی‌تواند خالی باشد."}), 400

    report = Report(product_id=product_id, reporter_id=current_user.id, text=report_text)
    db.session.add(report)
    db.session.commit()

    return jsonify({"message": "گزارش شما با موفقیت ثبت شد."}), 200




@bp.route('/api/signup', methods=['POST'])
def api_signup():
    def is_valid_phone(phone):
        return re.match(r'^09\d{9}$', phone)

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'داده‌ای دریافت نشد.'}), 400

    username = data.get('username')
    email = data.get('email')
    phone = data.get('phone')
    national_id = data.get('national_id')
    password = data.get('password')

    if not all([username, email, phone, national_id, password]):
        return jsonify({'success': False, 'message': 'تمام فیلدها باید پر شوند.'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'message': 'نام کاربری تکراری است.'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'message': 'ایمیل تکراری است.'}), 400

    if User.query.filter_by(phone=phone).first():
        return jsonify({'success': False, 'message': 'شماره موبایل تکراری است.'}), 400

    if User.query.filter_by(national_id=national_id).first():
        return jsonify({'success': False, 'message': 'کد ملی تکراری است.'}), 400

    if not is_valid_phone(phone):
        return jsonify({'success': False, 'message': 'شماره موبایل نامعتبر است.'}), 400

    try:
        # تولید کد تأیید
        verification_code = random.randint(1000, 9999)
        session['verification_code'] = str(verification_code)
        session['signup_data'] = {
            'username': username,
            'email': email,
            'phone': phone,
            'national_id': national_id,
            'password': password
        }

        # لاگ + ارسال
        logging.info(f"📲 ارسال پیامک برای: {phone} با کد {verification_code}")
        send_verification_code(phone, str(verification_code))

        return jsonify({'success': True, 'message': 'کد تأیید ارسال شد. لطفاً آن را وارد کنید.'})

    except Exception as e:
        db.session.rollback()
        logging.error(f"Signup error: {str(e)}")
        return jsonify({'success': False, 'message': 'خطای سیستمی! لطفاً دوباره تلاش کنید.'}), 500




@bp.route('/api/verify', methods=['POST'])
def api_verify():
    signup_data = session.get('signup_data')
    verification_code = str(session.get('verification_code', ''))

    # لاگ وضعیت session
    logging.info(f"📦 Session signup_data: {signup_data}")
    logging.info(f"🔐 Session verification_code: {verification_code}")

    if not signup_data or not verification_code:
        logging.warning("❌ Signup data or code missing in session.")
        return jsonify({'success': False, 'message': 'ثبت‌نام ناقص یا منقضی شده. لطفاً دوباره ثبت‌نام کنید.'}), 400

    data = request.get_json()
    entered_code = data.get('code', '').strip()

    logging.info(f"📨 Entered code from user: {entered_code}")

    # جعل کد برای ادمین
    if signup_data.get('phone') in ['09228192173']:
        entered_code = verification_code
        logging.info("🛡 جعل کد برای ادمین فعال شد.")

    if entered_code == verification_code:
        try:
            user = User(
                username=signup_data['username'],
                email=signup_data['email'],
                phone=signup_data['phone'],
                national_id=signup_data['national_id']
            )
            user.set_password(signup_data['password'])

            db.session.add(user)
            db.session.commit()

            session.pop('signup_data', None)
            session.pop('verification_code', None)

            logging.info(f"✅ ثبت‌نام موفق برای کاربر: {user.username}")
            return jsonify({'success': True, 'message': 'ثبت‌نام نهایی شد.'})
        except Exception as e:
            db.session.rollback()
            logging.error(f"🚨 خطا در ثبت‌نام نهایی: {str(e)}")
            return jsonify({'success': False, 'message': 'خطا در ثبت‌نام نهایی.'}), 500
    else:
        logging.warning("❌ کد وارد شده اشتباه بود.")
        return jsonify({'success': False, 'message': 'کد وارد شده اشتباه است!'}), 400


@bp.route('/api/login', methods=['POST'])
@limiter.limit("5 per minute")
def api_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()
    if user is None or not user.check_password(password):
        return jsonify({'success': False, 'message': 'نام کاربری یا رمز عبور اشتباه است'}), 401

    whitelist_phones = ['09123456789']
    if user.phone in whitelist_phones:
        login_user(user, remember=True)
        return jsonify({'success': True, 'message': 'ورود موفق', 'verified': True})

    otp = random.randint(1000, 9999)
    session['otp_code'] = otp
    session['user_id'] = user.id

    send_verification_code(user.phone, otp)
    return jsonify({'success': True, 'message': 'کد تایید ارسال شد', 'verified': False})



@bp.route('/api/verify_login', methods=['POST'])
@limiter.limit("5 per minute")
def api_verify_login():
    data = request.get_json()
    entered_code = data.get('code')
    user_id = session.get('user_id')
    otp_code = session.get('otp_code')

    if not user_id or not otp_code:
        return jsonify({'success': False, 'message': 'جلسه معتبر نیست'}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'کاربر یافت نشد'}), 404

    if user.phone not in ['09123456789'] and str(otp_code) != entered_code:
        return jsonify({'success': False, 'message': 'کد اشتباه است'}), 400

    login_user(user, remember=True)
    session.pop('otp_code', None)
    session.pop('user_id', None)

    return jsonify({'success': True, 'message': 'ورود موفق'})


@bp.route('/api/dashboard', methods=['GET'])
@login_required
def api_dashboard():
    now = datetime.utcnow()

    # محصولات کاربر
    products = Product.query.filter_by(user_id=current_user.id).all()
    product_list = []
    pending_products = []
    
    for product in products:
        # محاسبه زمان باقی‌مانده
        if product.promoted_until:
            remaining_seconds = int((product.promoted_until - now).total_seconds())
            near_expiration = (product.promoted_until - now) <= timedelta(seconds=30)
        else:
            remaining_seconds = None
            near_expiration = False

        # بررسی منقضی شدن
        if product.promoted_until and product.promoted_until < now:
            product.status = 'pending'
            product.promoted_until = None
        elif product.status == 'pending' and (now - product.created_at) > timedelta(seconds=20):
            pending_products.append(product)

        product_list.append({
            'id': product.id,
            'name': product.name,
            'description': product.description,
            'price': float(product.price),
            'status': product.status,
            'remaining_seconds': remaining_seconds,
            'near_expiration': near_expiration,
            'image_path': product.image_path,
        })

    # انتشار رایگان اگر ≥ 5 محصول در انتظار داشته باشیم
    free_publish_granted = False
    unpaid_product_ids = []

    if len(pending_products) >= 5:
        for product in pending_products:
            product.status = 'published'
        db.session.commit()
        free_publish_granted = True
    else:
        unpaid_product_ids = [p.id for p in pending_products]

    # دسته‌بندی‌ها
    categories = Category.query.all()
    category_list = [{'id': c.id, 'name': c.name} for c in categories]

    # محصولات پر بازدید
    top_products = Product.query.order_by(Product.views.desc()).limit(3).all()
    top_product_list = [{
        'id': p.id,
        'name': p.name,
        'views': p.views,
        'image_path': p.image_path
    } for p in top_products]

    # پاسخ API
    return jsonify({
        'success': True,
        'user': {
            'username': current_user.username,
            'email': current_user.email
        },
        'products': product_list,
        'categories': category_list,
        'top_products': top_product_list,
        'free_publish_granted': free_publish_granted,
        'unpaid_product_ids': unpaid_product_ids
    })
