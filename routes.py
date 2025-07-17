import os
from flask import render_template, redirect, url_for, flash, request, Blueprint, jsonify, session, url_for, current_app, abort, send_from_directory, request, make_response
from flask_login import login_user, logout_user, login_required, current_user
import secrets
import traceback
from urllib.parse import urlparse
from aplication import db
from models import User, Product, Category, EditProfileForm, Message, Conversation, Report, SignupTempData, ChatBotInteraction, ProductImage, bookmarks, UserReport, CooperationType, SalaryType, MilitaryStatus, MaritalStatus, EducationLevel, JobListing, JobProfile, WorkExperience, job_applications, JobListingReport, JobProfileReport, CategoryView, SearchHistory
from utils import save_image
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import logging
import random
import requests
from models import ProductType
from aplication import limiter
from sms_utils import send_verification_code
import re
import json
import urllib.parse
import base64
from flask_limiter.errors import RateLimitExceeded
from flask_limiter.util import get_remote_address
from sqlalchemy import case, func, or_, and_
from firebase_admin import messaging
from sqlalchemy.sql.expression import func




logging.basicConfig(level=logging.DEBUG)
bp = Blueprint('main', __name__)

def custom_key():
    return f"{get_remote_address()}-{request.form.get('username', '')}"



@bp.context_processor
def inject_enums_into_templates():
    return dict(
        CooperationType=CooperationType,
        SalaryType=SalaryType,
        MilitaryStatus=MilitaryStatus,
        MaritalStatus=MaritalStatus,
        EducationLevel=EducationLevel
        #WorkExperience=WorkExperience
    )


@limiter.limit("5 per minute")
@bp.route('/')
def index():
    search = request.args.get('search', '').strip()
    province_search = request.args.get('province_search', '').strip()
    city_search = request.args.get('city_search', '').strip()
    category_id = request.args.get('category', '').strip()
    address_search = request.args.get('address_search', '').strip()
    
    min_price = request.args.get('min_price', type=float, default=None)
    max_price = request.args.get('max_price', type=float, default=None)

    query = Product.query.filter(Product.status == 'published')


    selected_category = None
    if category_id:
        category = Category.query.get(category_id)
        if category:
            selected_category = category
            if category.subcategories: # If it's a parent category
                all_cat_ids = [sub.id for sub in category.subcategories] + [category.id]
                query = query.filter(Product.category_id.in_(all_cat_ids))
            else: # If it's a subcategory
                query = query.filter(Product.category_id == category_id)

    if province_search:
        query = query.filter(Product.address.ilike(f'%{province_search}%'))

    if city_search:
        query = query.filter(Product.address.ilike(f'%{city_search}%'))

    if address_search:
        query = query.filter(Product.address.ilike(f'%{address_search}%'))

    if category_id:
        query = query.filter(Product.category_id == category_id)

    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)




    relevance_score_expr = None
    if search:
        keywords = search.lower().split()
        relevance_score_expr = db.literal(0)
        search_filters = []

        for keyword in keywords:
            # امتیازدهی به هر کلمه کلیدی بر اساس محل تطابق
            keyword_score = case(
                (Product.name.ilike(keyword), 20),          # تطابق کامل نام (بیشترین امتیاز)
                (Product.name.ilike(f'{keyword}%'), 10),    # شروع نام با کلمه
                (Product.brand.ilike(f'%{keyword}%'), 8),   # وجود کلمه در برند
                (Product.name.ilike(f'%{keyword}%'), 5),     # وجود کلمه در نام
                (Product.description.ilike(f'%{keyword}%'), 1), # وجود کلمه در توضیحات (کمترین امتیاز)
                else_=0
            )
            relevance_score_expr += keyword_score

            # اطمینان از اینکه کلمه کلیدی حداقل در یکی از فیلدها وجود دارد
            search_filters.append(or_(
                Product.name.ilike(f'%{keyword}%'),
                Product.description.ilike(f'%{keyword}%'),
                Product.brand.ilike(f'%{keyword}%')
            ))
        
        query = query.filter(and_(*search_filters))
        query = query.add_columns(relevance_score_expr.label('relevance_score'))
        query = query.having(relevance_score_expr > 0)

    # مرتب‌سازی نهایی
    order_logic = [db.case((Product.promoted_until > datetime.utcnow(), 1), else_=0).desc()]
    if relevance_score_expr is not None:
        order_logic.append(relevance_score_expr.desc()) # مرتب‌سازی بر اساس امتیاز
    order_logic.append(Product.created_at.desc())
    
    query = query.order_by(*order_logic)
    
    results = query.all()
    
    # استخراج محصول از تاپل (محصول, امتیاز)
    products = [res[0] if isinstance(res, tuple) else res for res in results]



    recommended_products = []
    if current_user.is_authenticated:
        # ۱. پیدا کردن دسته‌بندی‌های محبوب (مثل قبل)
        favorite_categories_query = db.session.query(CategoryView.category_id)\
            .filter_by(user_id=current_user.id)\
            .group_by(CategoryView.category_id)\
            .order_by(func.count(CategoryView.category_id).desc())\
            .limit(3).all()
        favorite_category_ids = [cat[0] for cat in favorite_categories_query]

        # ۲. پیدا کردن آخرین جستجوهای کاربر (کلمات کلیدی و شهرها)
        recent_searches_query = db.session.query(SearchHistory)\
            .filter_by(user_id=current_user.id)\
            .order_by(SearchHistory.timestamp.desc())\
            .limit(5).all()
        
        # ساخت لیستی از شروط برای کوئری
        recommendation_conditions = []
        
        # اضافه کردن شرط برای دسته‌بندی‌های محبوب
        if favorite_category_ids:
            recommendation_conditions.append(Product.category_id.in_(favorite_category_ids))

        # اضافه کردن شروط برای جستجوهای اخیر
        for history in recent_searches_query:
            if history.search_term:
                recommendation_conditions.append(Product.name.ilike(f'%{history.search_term}%'))
            if history.city:
                recommendation_conditions.append(Product.address.ilike(f'%{history.city}%'))

        # اگر شرطی برای پیشنهاد وجود داشت، کوئری را اجرا کن
        if recommendation_conditions:
            recommendation_query = Product.query.filter(
                Product.status == 'published',
                or_(*recommendation_conditions) # ترکیب همه شروط با "یا"
            ).order_by(Product.created_at.desc()).limit(8) # افزایش محدودیت به ۸
            
            recommended_products = recommendation_query.all()

    # حالت جایگزین: اگر هیچ پیشنهادی یافت نشد، پربازدیدترین‌ها را نمایش بده
    if not recommended_products:
        top_products_query = Product.query.order_by(Product.views.desc()).limit(8)
        recommended_products = top_products_query.all()


    

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

    cities_with_products = []
    for province, cities in citiesByProvince.items():
        for city in cities:
            if Product.query.filter(Product.address.ilike(f'%{city}%')).first():
                cities_with_products.append(city)

    cities_with_products = list(set(cities_with_products))

    top_products = Product.query.order_by(Product.views.desc()).limit(3).all()

    if len(top_products) < 4:
        top_products = top_products[:1]
    

    categories = Category.query.filter_by(parent_id=None).all()
    return render_template('products.html', products=products, categories=categories, recommended_products=recommended_products, selected_category=selected_category, provinces=provinces,cities=cities_with_products, datetime=datetime, citiesByProvince=citiesByProvince, top_products=top_products)



def file_exists(image_path):
    if not image_path:
        return False
    full_path = os.path.join(current_app.static_folder, 'uploads', image_path)
    return os.path.exists(full_path)



# در فایل routes.py

# در فایل routes.py

# در فایل routes.py

# routes.py (فقط تابع live_search را جایگزین کنید)

# routes.py (فقط این تابع را جایگزین کنید)

@bp.route('/live_search')
def live_search():
    # دریافت تمام پارامترهای ارسالی از فرانت‌اند
    search = request.args.get('search', '').strip()
    city_search = request.args.get('city_search', '').strip() # FIX: این خط اضافه شد
    address_search = request.args.get('address_search', '').strip()
    category_id = request.args.get('category', '').strip()
    min_price_str = request.args.get('min_price', '').strip()
    max_price_str = request.args.get('max_price', '').strip()

    # ذخیره سابقه جستجو
    if current_user.is_authenticated and (search or city_search):
        history_entry = SearchHistory(
            user_id=current_user.id,
            search_term=search,
            city=city_search
        )
        db.session.add(history_entry)
        db.session.commit()

    query = Product.query.filter(Product.status == 'published')

    # اعمال سایر فیلترها
    # نکته: ما از address_search و city_search به صورت جداگانه استفاده می‌کنیم
    # اگر می‌خواهید هر دو اعمال شوند، می‌توانید منطق را ترکیب کنید.
    # در حال حاضر، address_search کلی‌تر است.
    if address_search:
        query = query.filter(Product.address.ilike(f'%{address_search}%'))
    elif city_search: # از elif استفاده می‌کنیم تا با address_search تداخل نکند
         query = query.filter(Product.address.ilike(f'%{city_search}%'))

    if category_id:
        query = query.filter(Product.category_id == category_id)
    try:
        if min_price_str:
            query = query.filter(Product.price >= float(min_price_str))
        if max_price_str:
            query = query.filter(Product.price <= float(max_price_str))
    except ValueError:
        pass

    # === شروع منطق جستجوی امتیازی با CASE (بدون تغییر) ===
    relevance_score_expr = None
    if search:
        keywords = search.lower().split()
        relevance_score_expr = db.literal(0)
        search_filters = []
        for keyword in keywords:
            keyword_score = case(
                (Product.name.ilike(keyword), 20),
                (Product.name.ilike(f'{keyword}%'), 10),
                (Product.brand.ilike(f'%{keyword}%'), 8),
                (Product.name.ilike(f'%{keyword}%'), 5),
                (Product.address.ilike(f'%{keyword}%'), 2),
                (Product.description.ilike(f'%{keyword}%'), 1),
                else_=0
            )
            relevance_score_expr += keyword_score
            search_filters.append(or_(
                Product.name.ilike(f'%{keyword}%'),
                Product.description.ilike(f'%{keyword}%'),
                Product.brand.ilike(f'%{keyword}%'),
                Product.address.ilike(f'%{keyword}%')
            ))
        query = query.filter(and_(*search_filters))
        query = query.add_columns(relevance_score_expr.label('relevance_score'))
        query = query.having(relevance_score_expr > 0)

    # مرتب‌سازی نهایی (بدون تغییر)
    order_logic = [db.case((Product.promoted_until > datetime.utcnow(), 1), else_=0).desc()]
    if relevance_score_expr is not None:
        order_logic.append(relevance_score_expr.desc())
    order_logic.append(Product.created_at.desc())
    
    query = query.order_by(*order_logic)
    
    results = query.all()
    
    # پردازش نتایج برای نمایش (بدون تغییر)
    products_to_render = []
    for res in results:
        p = res[0] if hasattr(res, '_fields') else res
        if p.images and len(p.images) > 0:
            p.first_image_path = p.images[0].image_path if file_exists(p.images[0].image_path) else None
        elif p.image_path and file_exists(p.image_path):
            p.first_image_path = p.image_path
        else:
            p.first_image_path = None
        products_to_render.append(p)

    logging.warning(f"Found {len(products_to_render)} products")
    return render_template('_product_list.html', products=products_to_render, datetime=datetime)


    

@bp.route('/bazaar-login')
def bazaar_login():
    client_id = os.getenv('BAZAAR_CLIENT_ID')
    redirect_uri = 'https://stockdivar.ir/bazaar-callback'
    state = secrets.token_hex(16)

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


    client_id = os.getenv('BAZAAR_CLIENT_ID')
    client_secret = os.getenv('BAZAAR_CLIENT_SECRET')
    redirect_uri = 'https://stockdivar.ir/bazaar-callback'

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
@bp.route('/login-with-phone', methods=['GET', 'POST'])
def login_with_phone():
    """
    Handles the new login flow with a phone number.
    - If the user exists, sends an OTP and redirects to verification.
    - If the user does not exist, redirects to the signup page.
    """
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()

        if not re.match(r'^09\d{9}$', phone):
            flash('شماره تماس نامعتبر است. باید با 09 شروع شده و 11 رقم باشد.', 'danger')
            return redirect(url_for('main.login_with_phone'))

        user = User.query.filter_by(phone=phone).first()

        if user:
            otp = random.randint(1000, 9999)
            session['otp_code'] = otp
            session['user_id'] = user.id
            session['otp_expiry'] = (datetime.utcnow() + timedelta(minutes=1)).timestamp()
            send_verification_code(user.phone, otp)
            
            flash('کد تایید برای شما ارسال شد. این کد به مدت ۱ دقیقه معتبر است.', 'info')
            return redirect(url_for('main.verify_login'))
        else:
            flash('این شماره در سیستم ثبت نشده است. لطفاً ابتدا ثبت نام کنید.', 'warning')
            return redirect(url_for('main.signup'))

    return render_template('login_phone.html')


@limiter.limit("5 per minute")
@bp.route('/verify_login', methods=['GET', 'POST'])
def verify_login():
    if 'user_id' not in session:
        flash('جلسه شما نامعتبر است. لطفا از ابتدا وارد شوید.', 'warning')
        return redirect(url_for('main.login_with_phone'))

    if request.method == 'POST':
        entered_code = request.form.get('code')
        user_id = session.get('user_id')
        otp_code = session.get('otp_code')
        otp_expiry = session.get('otp_expiry')

        if not user_id or not otp_code or not otp_expiry:
            flash('اطلاعات جلسه ناقص است. لطفاً دوباره وارد شوید.', 'danger')
            return redirect(url_for('main.login_with_phone'))
        
        if datetime.utcnow().timestamp() > otp_expiry:
            flash('کد تایید منقضی شده است. لطفاً کد جدید درخواست کنید.', 'danger')
            return redirect(url_for('main.verify_login'))

        user = User.query.get(user_id)
        if not user:
            flash('کاربر یافت نشد.', 'danger')
            return redirect(url_for('main.login_with_phone'))

        whitelist_phones = ['09123456789']
        
        if user.phone in whitelist_phones or entered_code == str(otp_code):
            login_user(user, remember=True)
            session.pop('otp_code', None)
            session.pop('user_id', None)
            session.pop('otp_expiry', None)
            flash('ورود با موفقیت انجام شد!', 'success')
            return redirect(url_for('main.index'))
        else:
            flash('کد وارد شده اشتباه است!', 'danger')
    
    time_left = 0
    otp_expiry = session.get('otp_expiry')
    if otp_expiry:
        time_left = max(0, int(otp_expiry - datetime.utcnow().timestamp()))

    return render_template('verify_login.html', time_left=time_left)


@bp.route('/resend-login-otp')
@limiter.limit("2 per minute")
def resend_login_otp():
    """
    یک کد تایید جدید برای کاربری که در حال ورود است ارسال می‌کند.
    """
    if 'user_id' not in session:
        flash('جلسه شما نامعتبر است. لطفاً از ابتدا شروع کنید.', 'danger')
        return redirect(url_for('main.login_with_phone'))

    user = User.query.get(session['user_id'])

    if not user:
        flash('کاربر یافت نشد.', 'danger')
        session.clear()
        return redirect(url_for('main.login_with_phone'))

    otp = random.randint(1000, 9999)
    session['otp_code'] = otp
    session['otp_expiry'] = (datetime.utcnow() + timedelta(minutes=1)).timestamp()
    send_verification_code(user.phone, str(otp))

    flash('کد تایید جدید برای شما ارسال شد.', 'info')
    return redirect(url_for('main.verify_login'))





@limiter.limit("5 per minute")
@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@bp.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    logging.debug("🏁 Dashboard function started")
    products = Product.query.filter_by(user_id=current_user.id).all()
    saved_products = current_user.saved_products.order_by(bookmarks.c.product_id.desc()).all()

    user_job_listings = JobListing.query.filter_by(user_id=current_user.id).order_by(JobListing.created_at.desc()).all()
    user_job_profile = JobProfile.query.filter_by(user_id=current_user.id).first()
    
    now = datetime.utcnow()
    for product in products:
        logging.debug(f"📦 بررسی محصول: {product.name} | promoted_until: {product.promoted_until}")
        
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

    categories = Category.query.all()
    
    form = EditProfileForm(obj=current_user)
    if form.validate_on_submit():
        new_phone = form.phone.data.strip()
        if new_phone != current_user.phone:
            existing_user = User.query.filter_by(phone=new_phone).first()
            if existing_user:
                flash('این شماره تماس قبلاً ثبت شده است.', 'danger')
                return redirect(url_for('main.dashboard'))
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
        
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        flash('اطلاعات شما با موفقیت بروزرسانی شد!')
        return redirect(url_for('main.dashboard'))
    top_products = Product.query.order_by(Product.views.desc()).limit(3).all()
    if len(top_products) < 4:
        top_products = top_products[:1]

    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        flash('اطلاعات شما با موفقیت بروزرسانی شد!')
        return redirect(url_for('main.dashboard'))

    can_promote = len(products) >= 5

    blocked_products = [p for p in products if p.status == 'blocked']

    
    return render_template(
        'dashboard.html', 
        products=products, 
        categories=categories, 
        form=form, 
        top_products=top_products,
        free_publish_granted=free_publish_granted,
        unpaid_product_ids=unpaid_product_ids,
        can_promote=can_promote,
        now=datetime.utcnow(),
        saved_products=saved_products,
        blocked_products=blocked_products,
        user_job_listings=user_job_listings,
        user_job_profile=user_job_profile
    )



@bp.route('/toggle_bookmark/<int:product_id>', methods=['POST'])
@login_required
def toggle_bookmark(product_id):
    product = Product.query.get_or_404(product_id)

    if product in current_user.saved_products:
        current_user.saved_products.remove(product)
        db.session.commit()
        return jsonify({'status': 'success', 'action': 'removed'})
    else:
        current_user.saved_products.append(product)
        db.session.commit()
        return jsonify({'status': 'success', 'action': 'added'})
    


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



@bp.route('/store/<int:user_id>')
def store(user_id):
    """
    نمایش صفحه فروشگاه یک کاربر خاص با تمام محصولات منتشر شده او.
    """
    seller = User.query.get_or_404(user_id)
    
    products = Product.query.filter_by(user_id=seller.id, status='published').order_by(Product.created_at.desc()).all()
    
    return render_template('store.html', seller=seller, products=products)



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
    user = User.query.get_or_404(user_id)
    
    if current_user.id == user.id or current_user.is_admin:
        products = Product.query.filter_by(user_id=user.id).all()
        return render_template('user_dashboard.html', products=products, user=user)
    
    flash("شما به این داشبورد دسترسی ندارید")
    return redirect(url_for('main.dashboard'))  # به صفحه اصلی هدایت می‌شود



import requests
import os

def moderate_product_content(product_name, product_description, image_url):
    """
    محتوای محصول (متن و تصویر) را با استفاده از API های AvalAI بررسی می‌کند.
    """
    api_key = os.getenv("AVALAI_API_KEY")
    if not api_key:
        return False, "کلید API تعریف نشده است."

    try:
        text_to_check = [product_name, product_description]
        moderation_response = requests.post(
            "https://api.avalai.ir/v1/moderations",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"input": text_to_check, "model": "omni-moderation-latest"}, # از مدل omni استفاده می‌کنیم که قوی‌تر است
            timeout=20
        )
        
        if moderation_response.status_code == 200:
            results = moderation_response.json().get('results', [])
            for res in results:
                if res.get('flagged'):
                    flagged_categories = [cat for cat, flagged in res.get('categories', {}).items() if flagged]
                    reason = f"محتوای متنی به دلیل زیر نامناسب تشخیص داده شد: {', '.join(flagged_categories)}"
                    print(f"محصول رد شد: {reason}")
                    return False, reason
        else:
            print(f"خطا در API نظارت متن: {moderation_response.text}")
            return False, "سرویس نظارت بر متن پاسخگو نبود."

    except Exception as e:
        print(f"خطا در فرآیند نظارت بر متن: {e}")
        return False, "خطای داخلی در زمان بررسی متن."

    print("مرحله 1: بررسی متن با موفقیت انجام شد.")

    if not image_url or image_url == "No Image Provided":
        return True, "تایید شد (بدون عکس)."

    try:
        vision_model = "gpt-image-1"
        
        prompt_text = (
            "شما یک ناظر محتوای هوشمند هستید. آیا این تصویر شامل محتوای غیرقانونی، خشونت‌آمیز، مستهجن، "
            "کلاهبرداری یا موارد نامناسب دیگر برای یک فروشگاه آنلاین است؟ فقط با 'YES' یا 'NO' پاسخ بده."
        )

        vision_payload = {
            "model": vision_model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            }],
            "max_tokens": 5
        }
        
        vision_response = requests.post(
            "https://api.avalai.ir/v1/chat/completions", # Endpoint مدل‌های چت/بینایی
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=vision_payload,
            timeout=45
        )

        if vision_response.status_code == 200:
            answer = vision_response.json()["choices"][0]["message"]["content"].strip().upper()
            if "YES" in answer:
                reason = "تصویر محصول نامناسب تشخیص داده شد."
                print(f"محصول رد شد: {reason}")
                return False, reason
            else:
                print("مرحله 2: بررسی تصویر با موفقیت انجام شد.")
                return True, "محصول پس از بررسی کامل تایید شد."
        else:
            print(f"خطا در API بینایی: {vision_response.text}")
            return False, "سرویس نظارت بر تصویر پاسخگو نبود."
            
    except Exception as e:
        print(f"خطا در فرآیند نظارت بر تصویر: {e}")
        return False, "خطای داخلی در زمان بررسی تصویر."




@limiter.limit("5 per minute")
@bp.route('/product/new', methods=['GET', 'POST'])
@login_required
def new_product():
    if request.method == 'POST':
        try:
            # گرفتن داده‌ها از فرم
            name = request.form.get('name')
            description = request.form.get('description')
            price_from_form = request.form.get('price', '0')
            price = price_from_form.replace(',', '')
            category_id = request.form.get('category_id')
            product_type = request.form.get('product_type')
            province = request.form.get("province")
            city = request.form.get("city")
            address = f"{province}-{city}"
            postal_code = request.form.get("postal_code")
            brand = request.form.get('brand')
            uploaded_image_paths_str = request.form.get('uploaded_image_paths')
            image_paths = uploaded_image_paths_str.split(',') if uploaded_image_paths_str else []
            main_image_path = image_paths[0] if image_paths else None

            # بررسی و ذخیره تصویر
            image_path = request.form.get('uploaded_image_path')

            # ایجاد و ذخیره محصول جدید در دیتابیس
            product = Product(
                name=name,
                description=description,
                price=float(price),
                image_path=main_image_path,
                user_id=current_user.id,
                category_id=category_id,
                address=address,
                postal_code=postal_code,
                product_type=ProductType[product_type] if product_type in ProductType.__members__ else None,
                brand=brand,
                status='pending'
            )

            db.session.add(product)
            db.session.flush()

            for path in image_paths:
                if path:
                    product_image = ProductImage(image_path=path.strip(), product_id=product.id)
                    db.session.add(product_image)
            
            db.session.commit()

            image_full_url = url_for('main.uploaded_file', filename=product.image_path, _external=True) if product.image_path else "No Image Provided"
            
            is_approved, reason = moderate_product_content(product.name, product.description, image_full_url)
            
            if is_approved:
                product.status = 'published'
                db.session.commit()
                flash('محصول شما پس از بررسی خودکار، با موفقیت منتشر شد!', 'success')
            else:
                flash(f'محصول شما برای بررسی بیشتر توسط ادمین ثبت شد.', 'warning')
                print(f"محصول '{product.name}' توسط AI رد شد: {reason}")

            user_agent = request.headers.get('User-Agent', '').lower()
            if 'wv' in user_agent or 'android' in user_agent:
                return render_template('upload_success.html')
            else:
                flash('محصول با موفقیت ایجاد شد و در انتظار تأیید است.', 'success')
                return redirect(url_for('main.dashboard'))

        except Exception as e:
            db.session.rollback()
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
            price_from_form = request.form.get('price', '0')
            product.price = float(price_from_form.replace(',', ''))

            province = request.form.get("province")
            city = request.form.get("city")
            product.address = f"{province}-{city}"

            product.postal_code = request.form.get("postal_code")
            product.brand = request.form.get('brand')


            product_type = request.form.get("product_type")
            if product_type in ProductType.__members__:
                product.product_type = ProductType[product_type]
            else:
                product.product_type = None

            uploaded_image_paths_str = request.form.get('uploaded_image_paths')
            image_paths = uploaded_image_paths_str.split(',') if uploaded_image_paths_str else []

            ProductImage.query.filter_by(product_id=product.id).delete()

            for path in image_paths:
                if path:
                    product_image = ProductImage(image_path=path.strip(), product_id=product.id)
                    db.session.add(product_image)

            product.image_path = image_paths[0] if image_paths else None


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

    product_province = product.address.split('-')[0] if product.address else ''
    product_city = product.address.split('-')[1] if '-' in product.address else ''

    categories = Category.query.all()

    response = make_response(render_template('product_form.html', product=product, categories=categories, provinces=provinces, citiesByProvince=citiesByProvince, product_province=product_province, product_city=product_city))
    
    # اضافه کردن هدرهای ضد کش فقط به این پاسخ
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response



@limiter.limit("5 per minute")
@bp.route('/product/<int:id>/delete', methods=['POST'])
@login_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    if product.user_id != current_user.id and not current_user.is_admin:
        flash('شما اجازه حذف این محصول را ندارید')
        return redirect(url_for('main.dashboard'))

    try:
        image_files_to_delete = []
        if product.image_path:
            image_files_to_delete.append(product.image_path)
        for img in product.images:
            image_files_to_delete.append(img.image_path)
        
        for filename in set(image_files_to_delete):
            if filename:
                try:
                    image_path_full = os.path.join(current_app.root_path, 'static/uploads', filename)
                    if os.path.exists(image_path_full):
                        os.remove(image_path_full)
                except Exception as e:
                    logging.error(f"Error deleting image file {filename}: {str(e)}")

        db.session.delete(product)
        db.session.commit()
        flash('محصول با موفقیت حذف شد')

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error deleting product object: {str(e)}")
        flash('خطا در حذف محصول')

    return redirect(url_for('main.dashboard'))





@limiter.limit("5 per minute")
@bp.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)


    if current_user.is_authenticated:
        five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)
        last_view = CategoryView.query.filter(
            CategoryView.user_id == current_user.id,
            CategoryView.category_id == product.category_id,
            CategoryView.timestamp > five_minutes_ago
        ).first()
        
        if not last_view:
            view = CategoryView(user_id=current_user.id, category_id=product.category_id)
            db.session.add(view)
            db.session.commit()


    similar_products = Product.query.filter(
        Product.category_id == product.category_id,
        Product.id != product.id,
        Product.status == 'published'
    ).order_by(func.random()).limit(10).all()
    categories = Category.query.all()
    user = User.query.get(product.user_id)
    phone = user.phone if user else None
    return render_template('product_detail.html', user=user, product=product, categories=categories, phone=phone, similar_products=similar_products)




@limiter.limit("5 per minute")
@bp.route('/init-categories')
def init_categories():
    categories = [
        {'name': 'ابزار کرگیری', 'icon': 'bi-drill', 'subcategories': [
            {'name': 'دریل', 'icon': 'bi-wrench'},
            {'name': 'فرز', 'icon': 'bi-gear'},
            {'name': 'کمپرسور', 'icon': 'bi-wind'}
        ]},
        {'name': 'بتن کن', 'icon': 'bi-hammer', 'subcategories': []},
        {'name': 'ابزار اندازه گیری', 'icon': 'bi-rulers', 'subcategories': [
            {'name': 'اره', 'icon': 'bi-tree'},
            {'name': 'چمن‌زن', 'icon': 'bi-flower3'}
        ]},
        {'name': 'مته و قلم', 'icon': 'bi-tools', 'subcategories': [
            {'name': 'جک هیدرولیک', 'icon': 'bi-car-front'},
            {'name': 'آچار بکس', 'icon': 'bi-wrench-adjustable'}
        ]},
        {'name': 'سیستم میخکوب ها', 'icon': 'bi-hammer', 'subcategories': []},
        {'name': 'ابزار برقی', 'icon': 'bi-lightning-charge', 'subcategories': []},
        {'name': 'ابزار شارژی', 'icon': 'bi-battery-full', 'subcategories': []},
        {'name': 'ابزار دستی', 'icon': 'bi-battery-full', 'subcategories': []},
        {'name': 'متفرقه', 'icon': 'bi-battery-full', 'subcategories': []},
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






@bp.route('/categories')
def categories_page():
    """
    صفحه‌ای برای نمایش دسته‌بندی‌ها و محصولات مرتبط با آن‌ها.
    - اگر category_id در URL نباشد، فقط لیست دسته‌بندی‌ها نمایش داده می‌شود.
    - اگر category_id باشد، محصولات آن دسته (و زیردسته‌هایش) نمایش داده می‌شود.
    """
    parent_categories = Category.query.filter_by(parent_id=None).order_by(Category.name).all()

    selected_category_id = request.args.get('category_id', type=int)
    
    selected_category = None
    products = []

    if selected_category_id:
        selected_category = Category.query.get_or_404(selected_category_id)
        
        if selected_category.subcategories:
            category_ids = [selected_category.id] + [sub.id for sub in selected_category.subcategories]
            products = Product.query.filter(
                Product.category_id.in_(category_ids),
                Product.status == 'published'
            ).order_by(Product.created_at.desc()).all()
        else:
            products = Product.query.filter_by(
                category_id=selected_category.id,
                status='published'
            ).order_by(Product.created_at.desc()).all()

    return render_template(
        'categories.html',
        parent_categories=parent_categories,
        selected_category=selected_category,
        products=products
    )






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

            if not all([username, phone, national_id, password]):
                flash('لطفاً تمام فیلدهای الزامی را پر کنید.', 'danger')
                return render_template('signup.html')

            if User.query.filter_by(username=username).first():
                flash('این نام کاربری قبلاً ثبت شده است.', 'danger')
                return render_template('signup.html')

            if email:
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

            session['signup_data'] = {
                'username': username,
                'email': email,
                'phone': phone,
                'national_id': national_id,
                'password': password
            }

            verification_code = random.randint(1000, 9999)
            session['verification_code'] = str(verification_code)

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

        if signup_data.get('phone') in admin_phones:
            entered_code = verification_code

        if entered_code == verification_code:
            email = signup_data.get('email')
            if not email:
                email = None

            user = User(
                username=signup_data['username'],
                email=email,
                phone=signup_data['phone'],
                national_id=signup_data['national_id']
            )
            user.set_password(signup_data['password'])

            db.session.add(user)
            db.session.commit()

            login_user(user)

            session.pop('verification_code', None)
            session.pop('signup_data', None)

            flash('.ثبت‌نام با موفقیت انجام شد و وارد شدید. قابلیت محصول گذاری رایگان برای شماره تماس شما فعال شد', 'success')
            return redirect(url_for('main.index'))  # یا هر صفحه دلخواه

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

        basic_auth_str = f"{client_id}:{client_secret}"
        basic_auth_bytes = basic_auth_str.encode("utf-8")
        basic_auth_b64 = base64.b64encode(basic_auth_bytes).decode("utf-8")
        headers = {
            "Authorization": f"Basic {basic_auth_b64}",
            "Content-Type": "application/x-www-form-urlencoded"
        }

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
    
    if product.user_id != current_user.id and not current_user.is_admin:
        flash('شما اجازه حذف نردبان این محصول را ندارید')
        return redirect(url_for('main.dashboard'))

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

    if product.user_id != current_user.id and not current_user.is_admin:
        flash('شما اجازه نردبان کردن این محصول را ندارید')
        return redirect(url_for('main.dashboard'))

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
    
    query = request.args.get('query', '').strip()
    role_filter = request.args.get('role_filter', '')
    pending_products = Product.query.filter_by(status='pending').all()
    users_dict = {u.id: u.username for u in User.query.all()}
    count = Product.query.count()
    total_users = User.query.count()

    users = User.query

    if query:
        users = users.filter(
            (User.username.ilike(f"%{query}%")) | 
            (User.email.ilike(f"%{query}%")) | 
            (User.phone.ilike(f"%{query}%")) | 
            (User.national_id.ilike(f"%{query}%"))
        )

    if role_filter == "admin":
        users = users.filter(User.is_admin == True)
    elif role_filter == "user":
        users = users.filter(User.is_admin == False)

    users = users.all()

    categories = Category.query.all()
    reports = Report.query.order_by(Report.created_at.desc()).all()
    user_reports = UserReport.query.order_by(UserReport.created_at.desc()).all()

    job_listing_reports = JobListingReport.query.order_by(JobListingReport.created_at.desc()).all()
    job_profile_reports = JobProfileReport.query.order_by(JobProfileReport.created_at.desc()).all()

    highly_reported_products = db.session.query(
        Product,
        func.count(Report.id).label('report_count')
    ).join(Report, Product.id == Report.product_id).group_by(Product.id).having(func.count(Report.id) >= 3).order_by(func.count(Report.id).desc()).all()

    logging.warning(f"محصولات گزارش شده یافت شده: {highly_reported_products}")

    blocked_products = Product.query.filter_by(status='blocked').order_by(Product.updated_at.desc()).all()

    return render_template("admin_dashboard.html", users=users, categories=categories, reports=reports, user_reports=user_reports, pending_products=pending_products, users_dict=users_dict, count=count, total_users=total_users, highly_reported_products=highly_reported_products, blocked_products=blocked_products, job_listing_reports=job_listing_reports, job_profile_reports=job_profile_reports)



@bp.route("/admin/search_blocked_products")
@login_required
def search_blocked_products():
    if not current_user.is_admin:
        return jsonify(error="Unauthorized"), 403

    query_term = request.args.get('q', '').strip()
    
    query = Product.query.filter_by(status='blocked')
    
    if query_term:
        query = query.join(User).filter(
            Product.name.ilike(f'%{query_term}%') |
            Product.description.ilike(f'%{query_term}%') |
            User.username.ilike(f'%{query_term}%')
        )
    
    products = query.order_by(Product.updated_at.desc()).all()
    
    return render_template('_blocked_products_list.html', products=products)



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



@bp.route("/admin/block_product/<int:product_id>", methods=["POST"])
@login_required
def block_product(product_id):
    if not current_user.is_admin:
        flash("شما دسترسی لازم برای این کار را ندارید", "danger")
        return redirect(url_for('main.index'))

    product = Product.query.get_or_404(product_id)
    product.status = 'blocked'
    db.session.commit()
    
    flash(f"محصول '{product.name}' با موفقیت مسدود شد.", "warning")
    return redirect(url_for('main.product_detail', product_id=product_id))


@bp.route("/admin/unblock_product/<int:product_id>", methods=["POST"])
@login_required
def unblock_product(product_id):
    if not current_user.is_admin:
        flash("شما دسترسی لازم برای این کار را ندارید", "danger")
        return redirect(url_for('main.index'))

    product = Product.query.get_or_404(product_id)
    product.status = 'published'
    db.session.commit()
    
    flash(f"محصول '{product.name}' با موفقیت از حالت مسدود خارج و منتشر شد.", "success")
    return redirect(url_for('main.product_detail', product_id=product_id))




active_sessions = {}

@bp.before_request
def track_user():
    session.permanent = True
    session.modified = True
    session_id = session.get('id')
    if not session_id:
        session['id'] = str(datetime.utcnow().timestamp())
    active_sessions[session['id']] = datetime.utcnow()

@bp.route('/online-users')
def online_users():
    now = datetime.utcnow()
    timeout = timedelta(minutes=5)
    active = {k: v for k, v in active_sessions.items() if now - v < timeout}
    return jsonify({'count': len(active)})



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
    user.is_admin = True
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
    user.is_admin = False
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

    # لیست شماره تلفن‌های محافظت شده
    protected_phones = ['09228192173', '09910689541', '09352499191', '09122719204', '09059124214']

    # بررسی اینکه آیا کاربر مورد نظر در لیست محافظت شده قرار دارد یا خیر
    if user.phone in protected_phones:
        flash(f"کاربر '{user.username}' محافظت شده است و قابل حذف نیست.", "danger")
        return redirect(url_for('main.admin_dashboard'))

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
    track_id = "123456789"
    return jsonify({"result": 100, "trackId": track_id})


    return render_template('signup.html')





@bp.route('/pay-to-publish/<int:product_id>', methods=['POST'])
def pay_to_publish(product_id):
    product = Product.query.get_or_404(product_id)
    if product.status == 'awaiting_payment':
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



def send_fcm_notification(token, title, body, data=None):
    """
    یک نوتیفیکیشن به یک توکن خاص دستگاه ارسال می‌کند.
    """
    if not token:
        logging.warning("تلاش برای ارسال نوتیفیکیشن بدون توکن.")
        return False
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            token=token,
            data=data or {},
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    sound='default',
                    click_action='FLUTTER_NOTIFICATION_CLICK'
                )
            )
        )
        response = messaging.send(message)
        logging.info(f"نوتیفیکیشن با موفقیت ارسال شد: {response}")
        return True
    except Exception as e:
        if isinstance(e, messaging.UnregisteredError):
            User.query.filter_by(fcm_token=token).update({'fcm_token': None})
            db.session.commit()
            logging.warning(f"توکن نامعتبر {token} از دیتابیس حذف شد.")
        else:
            logging.error(f"خطا در ارسال نوتیفیکیشن FCM: {e}")
        return False


@bp.route('/api/update_fcm_token', methods=['POST'])
@login_required
def update_fcm_token():
    data = request.get_json()
    token = data.get('token')
    if not token:
        return jsonify({'error': 'توکن ارسال نشده است'}), 400

    User.query.filter_by(fcm_token=token).update({'fcm_token': None})
    
    current_user.fcm_token = token
    db.session.commit()
    
    logging.info(f"توکن FCM برای کاربر {current_user.username} آپدیت شد.")
    return jsonify({'success': 'توکن با موفقیت آپدیت شد'}), 200





@bp.route('/api/unread_status')
@login_required
def unread_status():
    """
    تعداد کل پیام‌های خوانده‌نشده و تعداد تفکیکی برای هر گفتگو را برمی‌گرداند.
    """
    total_unread = Message.query.filter_by(
        receiver_id=current_user.id, 
        is_read=False
    ).count()

    return jsonify({
        'total_unread_count': total_unread,
    })




@bp.route("/conversations")
@login_required
def conversations():
    convos = Conversation.query.filter(
        or_(Conversation.user1_id == current_user.id, Conversation.user2_id == current_user.id)
    ).all()

    unread_counts = {
        c.id: Message.query.filter_by(
            conversation_id=c.id,
            receiver_id=current_user.id,
            is_read=False
        ).count() for c in convos
    }

    return render_template("conversations.html", conversations=convos, unread_counts=unread_counts)



@bp.route("/conversation/<int:conversation_id>", methods=["GET", "POST"])
@login_required
def conversation(conversation_id):
    convo = Conversation.query.get_or_404(conversation_id)

    if current_user.id not in [convo.user1_id, convo.user2_id]:
        return "Unauthorized", 403

    try:
        Message.query.filter_by(
            conversation_id=conversation_id,
            receiver_id=current_user.id,
            is_read=False
        ).update({'is_read': True})
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطا در علامت زدن پیام‌ها به عنوان خوانده شده: {e}")

    if request.method == "POST":
        content = request.form.get("content", "").strip()
        file = request.files.get("file")
        filename = None

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
            file_path=filename
        )
        db.session.add(new_msg)
        db.session.commit()

        return redirect(url_for("main.conversation", conversation_id=conversation_id))

    messages = Message.query.filter_by(conversation_id=conversation_id).order_by(Message.timestamp.asc()).all()

    other_user = convo.user2 if current_user.id == convo.user1_id else convo.user1
    is_blocked = current_user.has_blocked(other_user)
    am_i_blocked = other_user.has_blocked(current_user)

    return render_template("chat.html", conversation=convo, messages=messages, is_blocked=is_blocked, am_i_blocked=am_i_blocked)



@bp.route("/start_conversation/<int:user_id>")
@login_required
def start_conversation(user_id):
    if current_user.id == user_id:
        return redirect(url_for("index"))

    existing = Conversation.query.filter(
        ((Conversation.user1_id == current_user.id) & (Conversation.user2_id == user_id)) |
        ((Conversation.user1_id == user_id) & (Conversation.user2_id == current_user.id))
    ).first()

    if existing:
        return redirect(url_for("main.conversation", conversation_id=existing.id))

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


@bp.route("/send_message", methods=["POST"])
@login_required
def send_message():
    data = request.form
    conversation_id = int(data.get("conversation_id"))
    content = data.get("content", "").strip()
    file = request.files.get("file")
    filename = None

    convo = Conversation.query.get_or_404(conversation_id)
    if current_user.id not in [convo.user1_id, convo.user2_id]:
        return jsonify({"error": "Unauthorized"}), 403

    if file and file.filename:
        filename = secure_filename(file.filename)
        file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
        file.save(file_path)

    receiver_id = convo.user2_id if current_user.id == convo.user1_id else convo.user1_id
    receiver = User.query.get(receiver_id)

    if current_user.has_blocked(receiver):
        return jsonify({"error": "شما این کاربر را مسدود کرده‌اید و نمی‌توانید پیام ارسال کنید."}), 403
        
    if receiver.has_blocked(current_user):
        return jsonify({"error": "شما توسط این کاربر مسدود شده‌اید و نمی‌توانید پیام ارسال کنید."}), 403

    new_msg = Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        content=content,
        conversation_id=conversation_id,
        file_path=filename
    )
    db.session.add(new_msg)
    db.session.commit()

    try:
        recipient = User.query.get(receiver_id)
        if recipient and recipient.fcm_token:
            title = f"پیام جدید از {current_user.username}"
            body = content if content else "یک فایل برای شما ارسال شد"
            
            notification_data = {
                'type': 'new_message',
                'conversation_id': str(conversation_id),
                'sender_id': str(current_user.id),
                'sender_name': current_user.username
            }
            
            send_fcm_notification(
                token=recipient.fcm_token,
                title=title,
                body=body,
                data=notification_data
            )
    except Exception as e:
        logging.error(f"خطا در صف ارسال نوتیفیکیشن برای پیام {new_msg.id}: {e}")

    return jsonify({
        "message_id": new_msg.id,
        "sender_id": current_user.id,
        "content": new_msg.content,
        "timestamp": new_msg.timestamp.strftime('%Y-%m-%d %H:%M'),
        "file_path": new_msg.file_path
    })



@bp.route('/block_user/<int:user_id>', methods=['POST'])
@login_required
def block_user(user_id):
    user_to_block = User.query.get_or_404(user_id)
    if user_to_block == current_user:
        flash("شما نمی‌توانید خودتان را مسدود کنید.", "danger")
        return redirect(request.referrer or url_for('main.index'))
    
    current_user.block(user_to_block)
    db.session.commit()
    flash(f"کاربر {user_to_block.username} با موفقیت مسدود شد.", "success")
    return redirect(request.referrer)


@bp.route('/unblock_user/<int:user_id>', methods=['POST'])
@login_required
def unblock_user(user_id):
    user_to_unblock = User.query.get_or_404(user_id)
    current_user.unblock(user_to_unblock)
    db.session.commit()
    flash(f"کاربر {user_to_unblock.username} از حالت مسدود خارج شد.", "success")
    return redirect(request.referrer)


@bp.route('/report_user/<int:user_id>/<int:conversation_id>', methods=['POST'])
@login_required
def report_user(user_id, conversation_id):
    reported_user = User.query.get_or_404(user_id)
    reason = request.form.get('reason')
    
    if not reason:
        flash("دلیل گزارش نمی‌تواند خالی باشد.", "danger")
        return redirect(request.referrer)
        
    report = UserReport(
        reporter_id=current_user.id,
        reported_id=reported_user.id,
        conversation_id=conversation_id,
        reason=reason
    )
    db.session.add(report)
    db.session.commit()
    
    flash("گزارش تخلف شما با موفقیت ثبت شد و توسط مدیران بررسی خواهد شد.", "success")
    return redirect(request.referrer)





@bp.route("/get_new_messages")
@login_required
def get_new_messages():
    convo_id = request.args.get("conversation_id", type=int)
    after_id = request.args.get("after_id", type=int, default=0)

    convo = Conversation.query.get_or_404(convo_id)
    if current_user.id not in [convo.user1_id, convo.user2_id]:
        return jsonify([])

    new_messages = Message.query.filter(
        Message.conversation_id == convo_id,
        Message.id > after_id,
        Message.sender_id != current_user.id
    ).order_by(Message.timestamp.asc()).all()

    return jsonify([
        {
            "id": m.id,
            "sender_id": m.sender_id,
            "content": m.content,
            "timestamp": m.timestamp.strftime('%Y-%m-%d %H:%M'),
            "file_path": m.file_path
        } for m in new_messages
    ])




@bp.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@bp.route("/privacy")
def privacy():
    return render_template("security.html")


@bp.route('/chatbot', methods=['GET'])
@login_required
def chatbot_page_render():
    return render_template('ai_chat.html', bot_response="درود! به پلتفرم استوک خوش آمدید. چه کمکی از دست من برمیاد؟!")


def intelligent_product_search(
    keywords: list = None,
    brand: str = None,
    product_type: str = None,
    category_id: int = None,
    min_price: float = None,
    max_price: float = None,
    price_target: float = None,
    price_tolerance: float = 0.2,
    sort_by: str = 'relevance',
    limit: int = 5
):
    """
    یک تابع جستجوی پیشرفته که پارامترهای استخراج شده توسط هوش مصنوعی را دریافت
    و محصولات مرتبط را بر اساس ترکیبی از کلمات کلیدی، فیلترها و امتیاز ارتباط، جستجو می‌کند.
    """
    if not any([keywords, brand, product_type, category_id, min_price, max_price, price_target]):
        return []

    query = Product.query.filter(Product.status == 'published')

    if brand:
        query = query.filter(Product.brand.ilike(f'%{brand}%'))
    
    if product_type:
        try:
            enum_product_type = ProductType[product_type]
            query = query.filter(Product.product_type == enum_product_type)
        except KeyError:
            pass
            
    if category_id:
        category = Category.query.get(category_id)
        if category:
            if category.subcategories:
                all_related_category_ids = [category.id] + [sub.id for sub in category.subcategories]
                query = query.filter(Product.category_id.in_(all_related_category_ids))
            else:
                query = query.filter(Product.category_id == category_id)

    if price_target:
        lower_bound = price_target * (1 - price_tolerance)
        upper_bound = price_target * (1 + price_tolerance)
        query = query.filter(Product.price.between(lower_bound, upper_bound))
    else:
        if min_price is not None:
            query = query.filter(Product.price >= min_price)
        if max_price is not None:
            query = query.filter(Product.price <= max_price)

    relevance_score = None
    if keywords:
        # New approach: Combine conditions for keywords with AND, and also apply OR for each field
        # This will ensure products contain ALL keywords, but can be in different fields
        
        keyword_filters = []
        for kw in keywords:
            # Each keyword must be present in at least one of these fields (name OR description OR brand OR address)
            keyword_filters.append(
                or_(
                    Product.name.ilike(f'%{kw}%'),
                    Product.description.ilike(f'%{kw}%'),
                    Product.brand.ilike(f'%{kw}%'),
                    Product.address.ilike(f'%{kw}%'),
                )
            )
        
        # Apply ALL keyword filters with AND. This makes search much more precise.
        # Products must match ALL provided keywords.
        if keyword_filters:
            query = query.filter(and_(*keyword_filters))

        # --- Relevance Scoring (still based on individual keyword matches for scoring) ---
        relevance_cases = []
        for kw in keywords:
            # Higher score for exact matches or matches in crucial fields
            relevance_cases.append(case((Product.name.ilike(f'{kw}'), 20), else_=0)) # Exact name match - HIGH SCORE
            relevance_cases.append(case((Product.name.ilike(f'%{kw}%'), 10), else_=0)) # Partial name match - Good score
            relevance_cases.append(case((Product.brand.ilike(f'{kw}'), 8), else_=0)) # Exact brand match
            relevance_cases.append(case((Product.brand.ilike(f'%{kw}%'), 3), else_=0)) # Partial brand match
            relevance_cases.append(case((Product.description.ilike(f'%{kw}%'), 1), else_=0))
            # relevance_cases.append(case((Category.name.ilike(f'%{kw}%'), 4), else_=0)) 
        
        relevance_score = sum(relevance_cases).label("relevance_score")
        query = query.add_columns(relevance_score)


    # --- بخش مرتب‌سازی (Ordering) ---
    if sort_by == 'relevance' and relevance_score is not None:
        query = query.having(relevance_score >= 5)
        
        query = query.order_by(relevance_score.desc(), Product.views.desc(), Product.created_at.desc())
    elif sort_by == 'price_asc':
        query = query.order_by(Product.price.asc())
    elif sort_by == 'price_desc':
        query = query.order_by(Product.price.desc())
    elif sort_by == 'newest':
        query = query.order_by(Product.created_at.desc())
    else:
        # Fallback to views and then creation date for general relevance
        query = query.order_by(Product.views.desc(), Product.created_at.desc())


    products = query.limit(limit).all()

    if relevance_score is not None:
        return [product for product, score in products] # having قبلاً فیلتر کرده
    else:
        return products


# Your find_related_products function (if still used as a fallback, which is less ideal with tool calls)
# This function is simpler and does not use the intelligent scoring or advanced filtering.
# It is better to rely on intelligent_product_search for all product searches from AI.
def find_related_products(query_text, limit=3):
    if not query_text:
        return []
    keywords = query_text.lower().split()
    if not keywords:
        return []
    search_conditions = []
    for kw in keywords:
        search_conditions.append(Product.name.ilike(f'%{kw}%'))
        search_conditions.append(Product.description.ilike(f'%{kw}%'))
        search_conditions.append(Product.brand.ilike(f'%{kw}%'))
    products = Product.query.filter(
        Product.status == 'published',
        db.or_(*search_conditions)
    ).order_by(Product.views.desc()).limit(limit).all()
    return products


@bp.route('/api/chatbot_ajax', methods=['POST'])
@login_required
def chatbot_ajax():
    data = request.get_json()
    if not data or 'query' not in data:
        current_app.logger.warning("درخواست JSON فاقد کلید 'query' بود.")
        return jsonify({'error': 'ساختار درخواست نامعتبر است.', 'detail': "کلید 'query' در بدنه درخواست یافت نشد."}), 400

    user_query = data.get('query', '').strip()

    if not user_query:
        current_app.logger.info("کاربر یک سوال خالی ارسال کرد.")
        return jsonify({'error': 'سؤال نمی‌تواند خالی باشد.', 'detail': 'متن سوال ارسال نشده است.'}), 400

    bot_response_content = "متاسفانه پاسخی دریافت نشد."
    products_info = []
    related_products_models = []

    avalai_api_key = current_app.config.get("AVALAI_API_KEY")
    avalai_model = current_app.config.get("AVALAI_CHAT_MODEL")

    if not avalai_api_key or not avalai_model:
        current_app.logger.error("کلید API یا نام مدل AvalAI در پیکربندی اپلیکیشن (app.config) تنظیم نشده یا خالی است.")
        bot_response_content = "خطا: سرویس چت در حال حاضر به دلیل مشکل در پیکربندی سرور در دسترس نیست."
        
        interaction = ChatBotInteraction(
            user_id=current_user.id,
            user_query=user_query,
            bot_response=bot_response_content,
            products_related=None
        )
        db.session.add(interaction)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"خطا در ذخیره تعامل (در بخش پیکربندی): {str(e)}", exc_info=True)
        return jsonify({'bot_response': bot_response_content, 'products': products_info})

    system_prompt_content = (
        "شما یک دستیار هوشمند متخصص برای پلتفرم 'استوک' (stockdivar.ir) هستید و هویت شما کاملاً به این پلتفرم گره خورده است. وظیفه اصلی شما پاسخ به سوالات کاربران در مورد خرید و فروش ابزارآلات نو و دست دوم است."
        " هر سوالی خارج از این حوزه را با احترام رد کرده و بگویید که فقط در زمینه ابزارآلات در استوک می‌توانید کمک کنید."
        " به هیچ عنوان از منابع یا وب‌سایت‌های دیگر اطلاعات ندهید و محصولی را معرفی نکنید."
        "* `keywords`: **همیشه کلمات کلیدی مرتبط با محصول را به صورت کاملاً دقیق و به زبان فارسی استخراج کن.** (مثال: برای 'دریل شارژی'، کلمات کلیدی باید ['دریل', 'شارژی'] باشند. از استخراج کلمات کلیدی عمومی‌تر یا نامربوط خودداری کن)."
        "\n\n"
        "**قوانین پاسخ‌دهی:**"
        "\n\n"
        "1. **درخواست اپلیکیشن:** اگر کاربر کلماتی مانند «دانلود»، «اپلیکیشن»، یا «برنامه» را پرسید، فقط و فقط این دو لینک را به صورت HTML ارسال کن:"
        " <a href='https://cafebazaar.ir/app/com.example.stockdivarapp' target='_blank'>دانلود از کافه بازار</a> و <a href='https://stockdivar.ir/ionicApp-server/app-release-final.apk' target='_blank'>دانلود مستقیم</a>."
        "\n\n"
        "2. **راهنمایی کلی:** اگر کاربر برای خرید راهنمایی کلی خواست (مثال: «چه دریلی برای خونه خوبه؟»)، به جای ارسال لینک، او را راهنمایی کن و ویژگی‌های مهم ابزارها را توضیح بده. هدف مشاوره است، نه ارجاع به لینک جستجو."
        "\n\n"
        "3. **جستجوی برند یا محصول:**"
        " - **اگر محصول دقیق پیدا شد:** اگر از طریق ابزارهای داخلی شناسه محصول را داشتی، لینک مستقیم محصول را به این شکل بده: 'می‌توانید <a href=\"https://stockdivar.ir/product/[ID محصول]\" target=\"_blank\">[نام محصول]</a> را اینجا ببینید.'"
        " - **اگر برند یا عبارت کلی جستجو شد:** اگر کاربر نام یک برند (مثلا 'بوش') یا یک دسته (مثلا 'فرز انگشتی') را گفت، در انتهای پاسخت لینک جستجوی آن را به این شکل قرار بده: '<a href=\"https://stockdivar.ir/?search=[نام لاتین برند یا نام فارسی محصول (عبارتی که کاربر پرسیده مثلا دریل شارژی)]\" target=\"_blank\">محصولات [نام فارسی برند یا عبارت] در استوک</a>'."
        "\n\n"
        "همیشه مودب باش و اطمینان حاصل کن که تمام تگ‌های <a> دارای `target='_blank'` هستند. از دادن وعده‌هایی که از آن مطمئن نیستی، خودداری کن."
        "\n\n"
        "4. **استخراج کلمات کلیدی برای جستجو:** اگر سوال کاربر به دنبال محصول است، کلمات کلیدی مهم برای جستجو در پایگاه داده را شناسایی کن. سپس این کلمات را در انتهای پاسخ خود، داخل یک تگ خاص به این شکل قرار بده: `[SEARCH_KEYWORDS: کلمه۱ کلمه۲ کلمه۳]`."
        " مثال: اگر کاربر پرسید «دریل شارژی ماکیتا برای کارهای خانگی»، در انتهای پاسخت بنویس: `[SEARCH_KEYWORDS: دریل شارژی ماکیتا خانگی]`."
        "**نکته مهم:** اگر کاربر به دنبال محصولی خاص (مثلا 'دریل') است، از معرفی محصولات کاملاً متفاوت و نامرتبط (مانند 'فرز' یا 'مینی سنگ') خودداری کن، مگر اینکه این محصولات به وضوح به عنوان جایگزین یا مرتبط توسط کاربر درخواست شده باشند. تمرکز اصلی بر ارائه دقیق‌ترین نتایج بر اساس نیت کاربر است."
    )
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_products",
                "description": "جستجو در پایگاه داده محصولات استوک بر اساس کلمات کلیدی، برند، محدوده قیمت و دسته‌بندی.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "لیستی از کلمات کلیدی برای جستجو در نام، توضیحات و برند محصولات."
                        },
                        "brand": {
                            "type": "string",
                            "description": "برند محصول (مثلا 'بوش', 'ماکیتا')."
                        },
                        "product_type": {
                            "type": "string",
                            "enum": [pt.name for pt in ProductType], # استفاده از enum models.py
                            "description": "نوع محصول (نو، استوک، دست دوم، نیاز به تعمیر جزئی)."
                        },
                        "min_price": {
                            "type": "number",
                            "description": "حداقل قیمت محصول."
                        },
                        "max_price": {
                            "type": "number",
                            "description": "حداکثر قیمت محصول."
                        },
                        "sort_by": {
                            "type": "string",
                            "enum": ["relevance", "price_asc", "price_desc", "newest"],
                            "default": "relevance",
                            "description": "نحوه مرتب‌سازی نتایج: 'relevance' (ارتباط), 'price_asc' (قیمت صعودی), 'price_desc' (قیمت نزولی), 'newest' (جدیدترین)."
                        },
                        "limit": {
                            "type": "integer",
                            "default": 10,
                            "description": "حداکثر تعداد محصولاتی که باید بازگردانده شود."
                        }
                    },
                    "required": ["keywords"]
                },
            },
        }
    ]

    try:
        messages_payload = [
            {"role": "system", "content": system_prompt_content},
            {"role": "user", "content": user_query}
        ]
        current_app.logger.debug(f"پیام ارسالی به AvalAI: {messages_payload}")

        response = requests.post(
            "https://api.avalai.ir/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {avalai_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": avalai_model,
                "messages": messages_payload,
                "tools": tools,
                "tool_choice": "auto",
                "max_tokens": 1000,
                "temperature": 0.7
            },
            timeout=30
        )
        current_app.logger.info(f"AvalAI API Status: {response.status_code}")
        current_app.logger.debug(f"AvalAI API Response (raw text summary): {response.text[:300]}")
        api_data = response.json()

        if response.status_code == 200:
            if "choices" in api_data and api_data["choices"]:
                choice = api_data["choices"][0]
                
                if "tool_calls" in choice["message"] and choice["message"]["tool_calls"] is not None and isinstance(choice["message"]["tool_calls"], list) and len(choice["message"]["tool_calls"]) > 0:
                    tool_calls = choice["message"]["tool_calls"]
                    tool_call = tool_calls[0]
                    
                    if tool_call["function"]["name"] == "search_products":
                        try:
                            args = json.loads(tool_call["function"]["arguments"])
                            current_app.logger.info(f"AI requested product search with args: {args}")

                            related_products_models = intelligent_product_search( #
                                keywords=args.get('keywords'),
                                brand=args.get('brand'),
                                product_type=args.get('product_type'),
                                min_price=args.get('min_price'),
                                max_price=args.get('max_price'),
                                sort_by=args.get('sort_by', 'relevance'),
                                limit=args.get('limit', 5)
                            )
                            
                            if related_products_models:
                                for p in related_products_models:
                                    products_info.append({
                                        'id': p.id,
                                        'name': p.name,
                                        'price': float(p.price) if p.price is not None else None,
                                        'image_url': url_for('main.uploaded_file', filename=p.image_path, _external=True, _scheme='https') if p.image_path else None
                                    })
                                tool_output = json.dumps(products_info)
                            else:
                                tool_output = json.dumps([])
                                current_app.logger.info("No products found for the AI's search query.")

                            messages_payload.append(choice["message"])
                            messages_payload.append({
                                "tool_call_id": tool_call["id"],
                                "role": "tool",
                                "name": "search_products",
                                "content": tool_output
                            })

                            second_response = requests.post(
                                "https://api.avalai.ir/v1/chat/completions",
                                headers={
                                    "Authorization": f"Bearer {avalai_api_key}",
                                    "Content-Type": "application/json"
                                },
                                json={
                                    "model": avalai_model,
                                    "messages": messages_payload,
                                    "max_tokens": 1000,
                                    "temperature": 0.7
                                },
                                timeout=30
                            )
                            second_api_data = second_response.json()
                            if "choices" in second_api_data and second_api_data["choices"] and "message" in second_api_data["choices"][0] and "content" in second_api_data["choices"][0]["message"]:
                                bot_response_content = second_api_data["choices"][0]["message"]["content"].strip()
                            else:
                                bot_response_content = "پاسخ نهایی از ربات ساختار معتبری نداشت."
                                current_app.logger.error(f"Invalid second response structure from AvalAI: {second_api_data}")

                        except json.JSONDecodeError:
                            bot_response_content = "خطا در پردازش پارامترهای ابزار. لطفاً دوباره تلاش کنید."
                            current_app.logger.error(f"JSONDecodeError in tool arguments: {tool_call['function']['arguments']}")
                        except Exception as e:
                            bot_response_content = f"خطا در فراخوانی ابزار جستجوی محصول: {str(e)}"
                            current_app.logger.error(f"Error executing search_products tool: {str(e)}", exc_info=True)
                    else:
                        bot_response_content = "ابزار درخواست شده ناشناخته است."
                        current_app.logger.warning(f"Unknown tool requested by AI: {tool_call['function']['name']}")
                else:
                    if "message" in choice and "content" in choice["message"]:
                        bot_response_content = choice["message"]["content"].strip()
                        search_query_for_products = user_query # پیش‌فرض
                        match = re.search(r'\[SEARCH_KEYWORDS: (.*?)\]', bot_response_content)
                        if match:
                            search_query_for_products = match.group(1).strip()
                            bot_response_content = re.sub(r'\[SEARCH_KEYWORDS: .*?\]', '', bot_response_content).strip()
                        
                        related_products_models = find_related_products(search_query_for_products, limit=3)
                        if related_products_models:
                            for p in related_products_models:
                                products_info.append({
                                    'id': p.id,
                                    'name': p.name,
                                    'price': float(p.price) if p.price is not None else None,
                                    'image_url': url_for('main.uploaded_file', filename=p.image_path, _external=True, _scheme='https') if p.image_path else None
                                })
                    else:
                        bot_response_content = "متاسفانه ساختار پاسخ دریافتی از سرویس چت نامعتبر بود."
                        current_app.logger.error(f"Invalid response structure from AvalAI: {api_data}")
            else:
                bot_response_content = "پاسخی از مدل هوش مصنوعی دریافت نشد."
                current_app.logger.error(f"No choices in AvalAI response: {api_data}")
        else:
            bot_response_content = f"خطا در ارتباط با سرویس چت AvalAI. کد وضعیت: {response.status_code}."
            try:
                error_details = response.json()
                if 'error' in error_details and 'message' in error_details['error']:
                    bot_response_content += f" پیام خطا: {error_details['error']['message']}"
                current_app.logger.error(f"خطای API از AvalAI: Status {response.status_code}, Body: {error_details if 'error_details' in locals() else response.text}")
            except ValueError:
                current_app.logger.error(f"خطای API از AvalAI (پاسخ غیر JSON): Status {response.status_code}, Body: {response.text}")

    except requests.exceptions.Timeout:
        bot_response_content = "پاسخ از سرویس چت با تاخیر مواجه شد. لطفاً کمی بعد دوباره تلاش کنید."
        current_app.logger.error("Timeout error connecting to AvalAI API.")
    except requests.exceptions.RequestException as e:
        bot_response_content = "خطا در برقراری ارتباط با سرویس چت. لطفاً از اتصال اینترنت خود مطمئن شوید."
        current_app.logger.error(f"Network error or other RequestException calling AvalAI API: {str(e)}")
    except Exception as e:
        bot_response_content = "یک خطای پیش‌بینی نشده در سرویس چت رخ داد. در حال بررسی هستیم."
        current_app.logger.error(f"An unexpected error occurred in chatbot_ajax: {str(e)}", exc_info=True)


    product_ids_str = ",".join(str(p.id) for p in related_products_models) if related_products_models else None
    
    interaction = ChatBotInteraction(
        user_id=current_user.id,
        user_query=user_query,
        bot_response=bot_response_content,
        products_related=product_ids_str
    )
    db.session.add(interaction)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"خطا در ذخیره تعامل در دیتابیس: {str(e)}", exc_info=True)

    return jsonify({
        'bot_response': bot_response_content,
        'products': products_info
    })







@bp.before_request
def before_request_handler():
    if current_user.is_authenticated and getattr(current_user, 'is_banned', False):
        if request.endpoint and request.endpoint not in ['main.banned', 'main.logout', 'static']:
            return redirect(url_for('main.banned'))

    session.permanent = True
    session.modified = True
    session_id = session.get('id')
    if not session_id:
        session['id'] = str(datetime.utcnow().timestamp())
    active_sessions[session['id']] = datetime.utcnow()


@bp.route("/banned")
@login_required
def banned():
    if not current_user.is_banned:
        return redirect(url_for('main.index'))
    return render_template('banned.html')


@bp.route("/admin/ban_user/<int:user_id>", methods=["POST"])
@login_required
def ban_user(user_id):
    if not current_user.is_admin:
        flash("شما دسترسی لازم برای این کار را ندارید", "danger")
        return redirect(url_for('main.admin_dashboard'))

    user_to_ban = User.query.get_or_404(user_id)
    
    if user_to_ban.is_admin:
        flash("شما نمی‌توانید یک ادمین را مسدود کنید.", "danger")
        return redirect(url_for('main.admin_dashboard'))

    user_to_ban.is_banned = True
    user_to_ban.ban_reason = "انتشار محتوای نامناسب"  # می‌توانید این دلیل را داینامیک کنید
    db.session.commit()
    flash(f"کاربر '{user_to_ban.username}' با موفقیت مسدود شد.", "success")
    return redirect(url_for('main.admin_dashboard'))


@bp.route("/admin/unban_user/<int:user_id>", methods=["POST"])
@login_required
def unban_user(user_id):
    if not current_user.is_admin:
        flash("شما دسترسی لازم برای این کار را ندارید", "danger")
        return redirect(url_for('main.admin_dashboard'))

    user_to_unban = User.query.get_or_404(user_id)
    user_to_unban.is_banned = False
    user_to_unban.ban_reason = None
    db.session.commit()
    flash(f"کاربر '{user_to_unban.username}' با موفقیت از مسدودیت خارج شد.", "success")
    return redirect(url_for('main.admin_dashboard'))


# @bp.route('/api/search_by_image_ajax', methods=['POST'])
# @login_required
# def search_by_image_ajax():
#     if 'image_file' not in request.files:
#         current_app.logger.warning("SearchByImage: فایل تصویری ارسال نشده است.")
#         return jsonify({'error': 'فایل تصویری ارسال نشده است.'}), 400

#     image_file = request.files['image_file']

#     if image_file.filename == '':
#         current_app.logger.warning("SearchByImage: فایلی انتخاب نشده است (نام فایل خالی).")
#         return jsonify({'error': 'فایلی انتخاب نشده است.'}), 400

#     allowed_extensions = {'png', 'jpg', 'jpeg', 'webp'}
#     filename = secure_filename(image_file.filename)
#     if '.' not in filename or filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
#         current_app.logger.warning(f"SearchByImage: فرمت فایل نامعتبر: {filename}")
#         return jsonify({'error': 'فرمت فایل تصویری نامعتبر است.'}), 400
        
#     image_bytes = image_file.read()

#     analyzed_keywords = []
#     bot_message_for_image = "خطا در تحلیل تصویر. لطفا دوباره تلاش کنید."

#     try:
#         #---------------------------------------------------------------------------
#         avalai_api_key = current_app.config.get("AVALAI_VISION_API_KEY")
#         avalai_vision_endpoint = "https://api.avalai.ir/v1/vision/detect_objects"      
#         files_payload = {'image': (filename, image_bytes, image_file.mimetype)}
#         headers_payload = {"Authorization": f"Bearer {avalai_api_key}"}
#         current_app.logger.info(f"SearchByImage: ارسال عکس به {avalai_vision_endpoint}")
#         response_vision = requests.post(
#             avalai_vision_endpoint,
#             headers=headers_payload,
#             files=files_payload,
#             timeout=45
#         )
#         response_vision.raise_for_status()
#         vision_data = response_vision.json()
#         current_app.logger.debug(f"SearchByImage: پاسخ از سرویس تحلیل تصویر: {vision_data}")
#         if vision_data.get("status") == "success" and "objects" in vision_data:
#             for obj in vision_data["objects"]:
#                 if obj.get("confidence", 0) > 0.5:
#                     analyzed_keywords.append(obj["name"])
#             if analyzed_keywords:
#                 bot_message_for_image = f"بر اساس تصویر، موارد زیر تشخیص داده شد: {', '.join(analyzed_keywords)}. در حال جستجوی محصولات مشابه..."
#             else:
#                 bot_message_for_image = "موردی در تصویر برای جستجو تشخیص داده نشد."
#         else:
#             bot_message_for_image = f"تحلیل تصویر موفقیت‌آمیز نبود. پیام سرور: {vision_data.get('message', 'نامشخص')}"
#         #------------------------------------------------------------------------------------
#         client = google.cloud.vision.ImageAnnotatorClient()
#         content = image_bytes
#         gcp_image = google.cloud.vision.Image(content=content)
#         response_gcp = client.label_detection(image=gcp_image)
#         if response_gcp.error.message:
#             raise Exception(f"Google Vision API error: {response_gcp.error.message}")
#         labels = response_gcp.label_annotations
#         for label in labels:
#             if label.score > 0.6:
#                 analyzed_keywords.append(label.description)
#         if analyzed_keywords:
#             bot_message_for_image = f"بر اساس تصویر، موارد زیر تشخیص داده شد: {', '.join(analyzed_keywords)}. در حال جستجوی محصولات مشابه..."
#         else:
#             bot_message_for_image = "موردی در تصویر برای جستجو تشخیص داده نشد."


        # current_app.logger.info(f"SearchByImage: فایل '{filename}' با نوع '{image_file.mimetype}' دریافت شد، شبیه‌سازی تحلیل...")
        # temp_keywords_from_filename = []
        # fn_lower = filename.lower()
        # common_brands = ["دریل", "drill", "هیلتی", "hilti", "بوش", "bosch", "ماکیتا", "makita", "رونیکس", "ronix"] # لیست برندها یا کلمات کلیدی مهم
        # for brand_kw in common_brands:
        #     if brand_kw in fn_lower:
        #         if brand_kw == "drill": temp_keywords_from_filename.extend(["دریل", "ابزار"])
        #         elif brand_kw == "دریل": temp_keywords_from_filename.extend(["دریل", "ابزار برقی"])
        #         elif brand_kw == "hilti": temp_keywords_from_filename.extend(["هیلتی", "ابزار"])
        #         elif brand_kw == "هیلتی": temp_keywords_from_filename.extend(["هیلتی", "ابزار ساختمانی"])
        #         elif brand_kw == "bosch": temp_keywords_from_filename.extend(["بوش", "ابزار"])
        #         elif brand_kw == "بوش": temp_keywords_from_filename.extend(["بوش", "لوازم خانگی", "ابزار"])
        #         else: temp_keywords_from_filename.append(brand_kw)
        
        # if temp_keywords_from_filename:
        #     analyzed_keywords = list(set(temp_keywords_from_filename))
        #     bot_message_for_image = f"بر اساس نام فایل، به نظر می‌رسد تصویر مربوط به '{', '.join(analyzed_keywords)}' باشد. در حال جستجو..."
        # else:
        #     analyzed_keywords = [] 
        #     bot_message_for_image = "کلمات کلیدی خاصی از نام فایل تصویر استخراج نشد."
        # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

    # except requests.exceptions.HTTPError as http_err:
    #     current_app.logger.error(f"SearchByImage: خطای HTTP در ارتباط با سرویس تحلیل تصویر: {http_err.response.text}", exc_info=True)
    #     bot_message_for_image = "خطا در تحلیل تصویر (خطای سرور سرویس تصویر)."
    # except requests.exceptions.RequestException as req_err:
    #     current_app.logger.error(f"SearchByImage: خطا در ارتباط با سرویس تحلیل تصویر: {req_err}", exc_info=True)
    #     bot_message_for_image = "خطا در ارتباط با سرویس تحلیل تصویر. لطفاً اتصال اینترنت و پیکربندی را بررسی کنید."
    # except Exception as e:
    #     current_app.logger.error(f"SearchByImage: خطای ناشناخته در طول تحلیل تصویر: {e}", exc_info=True)
    #     bot_message_for_image = "خطای داخلی پیش‌بینی نشده در پردازش تصویر رخ داد."
            
    # products_info = []
    # related_products_models = []

    # if analyzed_keywords:
    #     current_app.logger.info(f"SearchByImage: جستجو در محصولات برای کلمات کلیدی: {analyzed_keywords}")
    #     search_query_from_image = " ".join(analyzed_keywords) 
    #     related_products_models = find_related_products(search_query_from_image, limit=6)
        
    #     if related_products_models:
    #         if "تشخیص داده شد" in bot_message_for_image or "به نظر می‌رسد" in bot_message_for_image:
    #              bot_message_for_image += f" {len(related_products_models)} محصول مرتبط یافت شد."
    #         else:
    #             bot_message_for_image = f"بر اساس تحلیل تصویر، {len(related_products_models)} محصول مرتبط یافت شد."

    #         for p in related_products_models:
    #             products_info.append({
    #                 'id': p.id,
    #                 'name': p.name,
    #                 'price': float(p.price) if p.price is not None else None,
    #                 'image_url': url_for('main.uploaded_file', filename=p.image_path, _external=True, _scheme='https') if p.image_path else None
    #             })
    #     elif analyzed_keywords:
    #          bot_message_for_image = f"بر اساس تحلیل تصویر و کلمات کلیدی '{', '.join(analyzed_keywords)}'، محصول مشابهی در حال حاضر یافت نشد."
    # elif not analyzed_keywords and "خطا" not in bot_message_for_image :
    #     bot_message_for_image = "متاسفانه تحلیل تصویر نتیجه‌ای برای جستجو در بر نداشت. لطفا عکس دیگری را امتحان کنید."
        
    # return jsonify({
    #     'bot_response': bot_message_for_image,
    #     'products': products_info,
    #     'analyzed_keywords': analyzed_keywords
    # })



# @bp.route('/chatbot', methods=['GET', 'POST'])
# @login_required
# def chatbot_page():
#     bot_response_content = None

#     if request.method == 'POST':
#         user_query = request.form.get('query', '').strip()

#         if not user_query:
#             flash('سؤال نمی‌تواند خالی باشد.', 'warning')
#             return redirect(url_for('main.chatbot_page'))

#         avalai_api_key = current_app.config.get("AVALAI_API_KEY")
#         avalai_model = current_app.config.get("AVALAI_CHAT_MODEL")

#         current_app.logger.debug(f"DEBUG - AVALAI_API_KEY from app.config: '{avalai_api_key}'")
#         current_app.logger.debug(f"DEBUG - AVALAI_CHAT_MODEL from app.config: '{avalai_model}'")

#         if not avalai_api_key or not avalai_model:
#             current_app.logger.error("کلید API یا نام مدل AvalAI در پیکربندی اپلیکیشن (app.config) تنظیم نشده یا خالی است.")
#             bot_response_content = "خطا: سرویس چت در حال حاضر در دسترس نیست (پیکربندی سرور ناقص است)."
#             interaction = ChatBotInteraction(
#                 user_id=current_user.id,
#                 user_query=user_query,
#                 bot_response=bot_response_content
#             )
#             db.session.add(interaction)
#             db.session.commit()
#             return render_template('ai_chat.html', bot_response=bot_response_content)


#         try:
#             response = requests.post(
#                 "https://api.avalai.ir/v1/chat/completions",
#                 headers={
#                     "Authorization": f"Bearer {avalai_api_key}",
#                     "Content-Type": "application/json"
#                 },
#                 json={
#                     "model": avalai_model,
#                     "messages": [{"role": "user", "content": user_query}],
#                     "max_tokens": 1000,
#                     "temperature": 0.7
#                 },
#                 timeout=30
#             )

#             current_app.logger.debug(f"AvalAI API Status Code: {response.status_code}")
#             current_app.logger.debug(f"AvalAI API Response Text: {response.text}")

#             if response.status_code == 200:
#                 data = response.json()
#                 if "choices" in data and data["choices"] and "message" in data["choices"][0] and "content" in data["choices"][0]["message"]:
#                     bot_response_content = data["choices"][0]["message"]["content"]
#                 else:
#                     bot_response_content = "پاسخ دریافتی از سرویس چت ساختار معتبری نداشت."
#                     current_app.logger.error(f"Unexpected AvalAI response structure: {data}")
#             else:
#                 bot_response_content = f"خطا در ارتباط با سرویس چت AvalAI. کد وضعیت: {response.status_code}"
#                 try:
#                     error_details = response.json()
#                     current_app.logger.error(f"AvalAI API Error Details: {error_details}")
#                     if 'error' in error_details and 'message' in error_details['error']:
#                          bot_response_content += f" پیام: {error_details['error']['message']}"
#                 except ValueError:
#                     current_app.logger.error(f"AvalAI API Error (non-JSON response): {response.text}")


#         except requests.exceptions.Timeout:
#             bot_response_content = "پاسخ از سرویس چت با تاخیر مواجه شد. لطفاً دوباره تلاش کنید."
#             current_app.logger.error("Timeout error connecting to AvalAI API.")
#         except requests.exceptions.RequestException as e:
#             bot_response_content = "خطا در برقراری ارتباط با سرویس چت. لطفاً وضعیت شبکه خود را بررسی کنید."
#             current_app.logger.error(f"Network error or other RequestException calling AvalAI API: {str(e)}")
#         except Exception as e:
#             bot_response_content = "یک خطای پیش‌بینی نشده در سرویس چت رخ داد."
#             current_app.logger.error(f"An unexpected error occurred in chatbot_page: {str(e)}")


#         if bot_response_content is None:
#             bot_response_content = "پاسخی از ربات دریافت نشد (خطای داخلی)."

#         interaction = ChatBotInteraction(
#             user_id=current_user.id,
#             user_query=user_query,
#             bot_response=bot_response_content
#         )
#         db.session.add(interaction)
#         db.session.commit()

#     return render_template('ai_chat.html', bot_response=bot_response_content)



# def find_related_products(query):
#     # تجزیه و تحلیل  کاربر
#     keywords = query.lower().split()

#     products = Product.query.filter(
#         db.or_(
#             *[Product.name.ilike(f'%{kw}%') for kw in keywords],
#             *[Product.description.ilike(f'%{kw}%') for kw in keywords]
#         )
#     ).limit(5).all()

#     return products




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

#             return redirect(url_for('main.chat', user_id=user.id))
    
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
#     conversation = Conversation.query.filter(
#         (Conversation.user1_id == user_id) | 
#         (Conversation.user2_id == user_id)
#     ).first()
    
#     if conversation:
#         return conversation.id
#     else:
#         new_conversation = Conversation(user1_id=user_id, user2_id=user_id)  # مثال: فرض می‌کنیم هر دو کاربر یکسان‌اند
#         db.session.add(new_conversation)
#         db.session.commit()
#         return new_conversation.id

# @bp.route('/send_message', methods=['POST'])
# def send_message():
#     try:
#         content = request.form['content']
#         replied_to_id = request.form.get('replied_to_id')

#         conversation_id = get_conversation_id(current_user.id)

#         new_message = Message(content=content, sender_id=current_user.id, replied_to_id=replied_to_id, conversation_id=conversation_id)
#         db.session.add(new_message)
#         db.session.commit()

#         messages = Message.query.filter_by(conversation_id=conversation_id).all()

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
#         return jsonify({'success': False, 'error': str(e)}), 500
    

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


# @bp.route('/api/product/<int:product_id>')
# @limiter.limit("5 per minute")
# def api_product_detail(product_id):
#     try:
#         product = Product.query.get_or_404(product_id)
#         user = User.query.get(product.user_id)
#         category = Category.query.get(product.category_id)

#         return jsonify({
#             "id": product.id,
#             "name": product.name,
#             "description": product.description,
#             "price": product.price,
#             "address": product.address,
#             "postal_code": product.postal_code,
#             "views": product.views,
#             "created_at": product.created_at.isoformat() if product.created_at else None,
#             "promoted_until": product.promoted_until.isoformat() if product.promoted_until else None,
#             "status": product.status,
#             "product_type": str(product.product_type) if product.product_type else None,
#             "category": category.name if category else None,
#             "user": {
#                 "id": user.id,
#                 "phone": user.phone
#             } if user else None,
#             "image_url": url_for('main.uploaded_file', filename=product.image_path, _external=True)
#         })
    
#     except Exception as e:
#         print(f"Error in api_product_detail: {e}")
#         traceback.print_exc()
#         return jsonify({"error": "Internal server error"}), 500


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
        verification_code = random.randint(1000, 9999)
        session['verification_code'] = str(verification_code)
        session['signup_data'] = {
            'username': username,
            'email': email,
            'phone': phone,
            'national_id': national_id,
            'password': password
        }

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

    logging.info(f"📦 Session signup_data: {signup_data}")
    logging.info(f"🔐 Session verification_code: {verification_code}")

    if not signup_data or not verification_code:
        logging.warning("❌ Signup data or code missing in session.")
        return jsonify({'success': False, 'message': 'ثبت‌نام ناقص یا منقضی شده. لطفاً دوباره ثبت‌نام کنید.'}), 400

    data = request.get_json()
    entered_code = data.get('code', '').strip()

    logging.info(f"📨 Entered code from user: {entered_code}")

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

    products = Product.query.filter_by(user_id=current_user.id).all()
    product_list = []
    pending_products = []
    
    for product in products:
        if product.promoted_until:
            remaining_seconds = int((product.promoted_until - now).total_seconds())
            near_expiration = (product.promoted_until - now) <= timedelta(seconds=30)
        else:
            remaining_seconds = None
            near_expiration = False

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

    free_publish_granted = False
    unpaid_product_ids = []

    if len(pending_products) >= 5:
        for product in pending_products:
            product.status = 'published'
        db.session.commit()
        free_publish_granted = True
    else:
        unpaid_product_ids = [p.id for p in pending_products]

    categories = Category.query.all()
    category_list = [{'id': c.id, 'name': c.name} for c in categories]

    top_products = Product.query.order_by(Product.views.desc()).limit(3).all()
    top_product_list = [{
        'id': p.id,
        'name': p.name,
        'views': p.views,
        'image_path': p.image_path
    } for p in top_products]

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




# llllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllll
# llllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllll


@limiter.limit("5 per minute")
@bp.route("/my_store", methods=["GET", "POST"])
@login_required
def my_store():
    user_products = Product.query.filter_by(user_id=current_user.id).all()
    return render_template('my_store.html', products=user_products)


@bp.route('/test-height')
def test_height_page():
    """
    A simple route to render the height test page.
    """
    return render_template('test_height.html')








@bp.route('/product/new_job_ad_choice')
@login_required
def new_job_ad_choice():
    """
    کاربر را به صفحه‌ای هدایت می‌کند تا بین ثبت آگهی استخدام یا پروفایل کاریابی یکی را انتخاب کند.
    """
    return render_template('job_ad_choice.html')



@bp.route('/product/new_hiring_ad', methods=['GET', 'POST'])
@login_required
def new_hiring_ad():
    """
    ایجاد یک آگهی استخدام جدید.
    این تابع مسیر عکس را از یک فیلد پنهان در فرم می‌خواند که توسط آپلود AJAX پر شده است.
    """
    if request.method == 'POST':
        try:
            salary_min_str = request.form.get('salary_min')
            salary_max_str = request.form.get('salary_max')

            salary_min_int = int(salary_min_str) if salary_min_str and salary_min_str.isdigit() else None
            salary_max_int = int(salary_max_str) if salary_max_str and salary_max_str.isdigit() else None
            new_listing = JobListing(
                user_id=current_user.id,
                title=request.form.get('title'),
                description=request.form.get('description'),
                benefits=request.form.get('benefits'),
                cooperation_type=CooperationType[request.form.get('cooperation_type')],
                salary_type=SalaryType[request.form.get('salary_type')],
                salary_min=salary_min_int,
                salary_max=salary_max_int,
                has_insurance='has_insurance' in request.form,
                is_remote_possible='is_remote_possible' in request.form,
                working_hours=request.form.get('working_hours'),
                profile_picture=request.form.get('profile_picture'),
                location=request.form.get('location')
            )
            db.session.add(new_listing)
            db.session.commit()
            flash('آگهی استخدام شما با موفقیت ثبت شد.', 'success')
            return redirect(url_for('main.dashboard'))
        except Exception as e:
            db.session.rollback()
            logging.error(f"خطا در ایجاد آگهی استخدام: {e}")
            flash('خطایی در هنگام ثبت آگهی رخ داد. لطفا دوباره تلاش کنید.', 'danger')

    return render_template('hiring_form.html', job=None, CooperationType=CooperationType, SalaryType=SalaryType)


@bp.route('/job-listing/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_job_listing(id):
    """
    ویرایش یک آگهی استخدام موجود.
    """
    job = JobListing.query.get_or_404(id)
    if job.owner != current_user and not current_user.is_admin:
        abort(403)

    if request.method == 'POST':
        try:
            job.title = request.form.get('title')
            job.description = request.form.get('description')
            job.benefits = request.form.get('benefits')
            job.cooperation_type = CooperationType[request.form.get('cooperation_type')]
            job.salary_type = SalaryType[request.form.get('salary_type')]
            salary_min_str = request.form.get('salary_min')
            salary_max_str = request.form.get('salary_max')
            job.salary_min = int(salary_min_str) if salary_min_str and salary_min_str.isdigit() else None
            job.salary_max = int(salary_max_str) if salary_max_str and salary_max_str.isdigit() else None
            job.has_insurance = 'has_insurance' in request.form
            job.is_remote_possible = 'is_remote_possible' in request.form
            job.working_hours = request.form.get('working_hours')
            job.profile_picture = request.form.get('profile_picture')
            job.location = request.form.get('location')
            
            db.session.commit()
            flash('آگهی استخدام با موفقیت به‌روزرسانی شد.', 'success')
            return redirect(url_for('main.dashboard'))
        except Exception as e:
            db.session.rollback()
            logging.error(f"خطا در ویرایش آگهی استخدام: {e}")
            flash('خطایی در هنگام به‌روزرسانی رخ داد.', 'danger')
    
    return render_template('hiring_form.html', job=job, CooperationType=CooperationType, SalaryType=SalaryType)


@bp.route('/job-listing/<int:id>/delete', methods=['POST'])
@login_required
def delete_job_listing(id):
    """
    حذف یک آگهی استخدام و عکس مرتبط با آن.
    """
    job = JobListing.query.get_or_404(id)
    if job.owner != current_user and not current_user.is_admin:
        abort(403)

    JobListingReport.query.filter_by(job_listing_id=job.id).delete()
    
    if job.profile_picture and job.profile_picture != 'default.jpg':
        try:
            image_path = os.path.join(current_app.root_path, 'static/uploads', job.profile_picture)
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            logging.error(f"خطا در حذف فایل عکس آگهی استخدام: {e}")

    db.session.delete(job)
    db.session.commit()
    flash('آگهی استخدام با موفقیت حذف شد.', 'success')
    return redirect(url_for('main.dashboard'))



def save_resume(file):
    """
    فایل رزومه را در پوشه static/resumes ذخیره می‌کند و نام آن را برمی‌گرداند.
    **نکته:** مطمئن شوید پوشه‌ای به نام resumes در کنار پوشه uploads شما وجود دارد.
    """
    resume_folder = os.path.join(current_app.root_path, 'static/resumes')
    if not os.path.exists(resume_folder):
        os.makedirs(resume_folder)
        
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(file.filename)
    resume_fn = random_hex + f_ext
    resume_path = os.path.join(resume_folder, resume_fn)
    file.save(resume_path)
    return resume_fn




@bp.route('/product/new_job_profile', methods=['GET', 'POST'])
@login_required
def new_job_profile():
    """
    ایجاد پروفایل کاریابی جدید. این نسخه اصلاح شده و منطق ذخیره سوابق شغلی را نیز شامل می‌شود.
    """
    if JobProfile.query.filter_by(user_id=current_user.id).first():
        flash('شما قبلاً یک پروفایل کاریابی ثبت کرده‌اید. برای تغییر، آن را ویرایش کنید.', 'warning')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        try:
            
            picture_path = request.form.get('profile_picture')
            resume_path = None
            if 'resume_file' in request.files:
                file = request.files['resume_file']
                if file.filename != '':
                    resume_path = save_resume(file)

            birth_date_str = request.form.get('birth_date')
            birth_date_obj = datetime.strptime(birth_date_str, '%Y-%m-%d').date() if birth_date_str else None
            
            salary_min_str = request.form.get('requested_salary_min')
            salary_min_int = int(salary_min_str) if salary_min_str and salary_min_str.isdigit() else None

            salary_max_str = request.form.get('requested_salary_max')
            salary_max_int = int(salary_max_str) if salary_max_str and salary_max_str.isdigit() else None

            portfolio_links_list = [link.strip() for link in request.form.getlist('portfolio_link') if link.strip()]
            portfolio_links_str = ','.join(portfolio_links_list)

            
            new_profile = JobProfile(
                user_id=current_user.id,
                title=request.form.get('title'),
                description=request.form.get('description'),
                portfolio_links=portfolio_links_str,
                contact_phone=request.form.get('contact_phone'),
                contact_email=request.form.get('contact_email'),
                location=request.form.get('location'),
                birth_date=birth_date_obj,
                marital_status=MaritalStatus[request.form.get('marital_status')] if request.form.get('marital_status') else None,
                military_status=MilitaryStatus[request.form.get('military_status')] if request.form.get('military_status') else None,
                highest_education_level=EducationLevel[request.form.get('highest_education_level')] if request.form.get('highest_education_level') else None,
                education_status=request.form.get('education_status'),
                requested_salary_min=salary_min_int,
                requested_salary_max=salary_max_int,
                profile_picture=picture_path,
                resume_path=resume_path
            )
            db.session.add(new_profile)
            db.session.commit()

            form_experiences = {}
            for key, value in request.form.items():
                match = re.match(r'work_experiences-(\d+)-(\w+)', key)
                if match:
                    index, field = int(match.group(1)), match.group(2)
                    if index not in form_experiences: form_experiences[index] = {}
                    form_experiences[index][field] = value
            
            for data in form_experiences.values():
                if data.get('job_title'):
                    new_exp = WorkExperience(
                        profile_id=new_profile.id,
                        job_title=data.get('job_title'),
                        company_name=data.get('company_name'),
                        start_date=data.get('start_date'),
                        end_date=data.get('end_date')
                    )
                    db.session.add(new_exp)

            db.session.commit()
            
            flash('پروفایل کاریابی شما با موفقیت ایجاد شد.', 'success')
            return redirect(url_for('main.dashboard'))

        except Exception as e:
            db.session.rollback()
            logging.error(f"خطا در ایجاد پروفایل کاریابی: {e}")
            flash('یک خطای پیش‌بینی نشده رخ داد. لطفاً مقادیر ورودی خود را بررسی کرده و دوباره تلاش کنید.', 'danger')
            return render_template('job_seeker_form.html', profile=None)
            
    return render_template('job_seeker_form.html', profile=None)





@bp.route('/job-profile/edit', methods=['GET', 'POST'])
@login_required
def edit_job_profile():
    """
    ویرایش پروفایل کاریابی موجود. این نسخه تضمین می‌کند که تمام Enum ها به قالب ارسال شوند.
    """
    profile = JobProfile.query.filter_by(user_id=current_user.id).first_or_404()

    if request.method == 'POST':
        try:
            profile.title = request.form.get('title')
            profile.description = request.form.get('description')
            portfolio_links_list = [link.strip() for link in request.form.getlist('portfolio_link') if link.strip()]
            profile.portfolio_links = ','.join(portfolio_links_list)
            profile.contact_phone = request.form.get('contact_phone')
            profile.contact_email = request.form.get('contact_email')
            profile.location = request.form.get('location')
            birth_date_str = request.form.get('birth_date')
            profile.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date() if birth_date_str else None
            profile.marital_status = MaritalStatus[request.form.get('marital_status')] if request.form.get('marital_status') else None
            profile.military_status = MilitaryStatus[request.form.get('military_status')] if request.form.get('military_status') else None
            profile.highest_education_level = EducationLevel[request.form.get('highest_education_level')] if request.form.get('highest_education_level') else None
            profile.education_status = request.form.get('education_status')
            salary_min_str = request.form.get('requested_salary_min')
            profile.requested_salary_min = int(salary_min_str) if salary_min_str and salary_min_str.isdigit() else None
            salary_max_str = request.form.get('requested_salary_max')
            profile.requested_salary_max = int(salary_max_str) if salary_max_str and salary_max_str.isdigit() else None
            profile.profile_picture = request.form.get('profile_picture')

            if 'resume_file' in request.files:
                file = request.files['resume_file']
                if file.filename != '':
                    if profile.resume_path:
                        old_resume_path = os.path.join(current_app.root_path, 'static/resumes', profile.resume_path)
                        if os.path.exists(old_resume_path):
                            os.remove(old_resume_path)
                    profile.resume_path = save_resume(file)

            form_experiences = {}
            for key, value in request.form.items():
                match = re.match(r'work_experiences-(\d+)-(\w+)', key)
                if match:
                    index, field = int(match.group(1)), match.group(2)
                    if index not in form_experiences: form_experiences[index] = {}
                    form_experiences[index][field] = value
            
            db_experience_ids = {exp.id for exp in profile.work_experiences}
            form_experience_ids = {int(data['id']) for data in form_experiences.values() if data.get('id') and data.get('id').isdigit()}
            
            ids_to_delete = db_experience_ids - form_experience_ids
            if ids_to_delete:
                WorkExperience.query.filter(WorkExperience.id.in_(ids_to_delete)).delete(synchronize_session=False)

            for data in form_experiences.values():
                exp_id = data.get('id')
                if exp_id and exp_id.isdigit():
                    experience = WorkExperience.query.get(int(exp_id))
                    if experience and experience.profile_id == profile.id:
                        experience.job_title, experience.company_name, experience.start_date, experience.end_date = data.get('job_title'), data.get('company_name'), data.get('start_date'), data.get('end_date')
                elif data.get('job_title'):
                    new_exp = WorkExperience(profile_id=profile.id, job_title=data.get('job_title'), company_name=data.get('company_name'), start_date=data.get('start_date'), end_date=data.get('end_date'))
                    db.session.add(new_exp)
            
            db.session.commit()
            flash('پروفایل کاریابی شما با موفقیت به‌روزرسانی شد.', 'success')
            return redirect(url_for('main.dashboard'))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"خطا در ویرایش پروفایل کاریابی: {e}")
            flash('خطایی در هنگام ویرایش پروفایل رخ داد.', 'danger')
    
    return render_template('job_seeker_form.html', 
                           profile=profile,
                           MaritalStatus=MaritalStatus,
                           MilitaryStatus=MilitaryStatus,
                           EducationLevel=EducationLevel)




@bp.route('/job-profile/delete', methods=['POST'])
@login_required
def delete_job_profile():
    """
    حذف پروفایل کاریابی و فایل‌های ضمیمه آن (عکس و رزومه).
    """
    profile = JobProfile.query.filter_by(user_id=current_user.id).first_or_404()
    
    if profile.profile_picture and profile.profile_picture != 'default.jpg':
        try:
            image_path = os.path.join(current_app.root_path, 'static/uploads', profile.profile_picture)
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            logging.error(f"خطا در حذف عکس پروفایل کاریابی: {e}")
    
    if profile.resume_path:
        try:
            resume_path = os.path.join(current_app.root_path, 'static/resumes', profile.resume_path)
            if os.path.exists(resume_path):
                os.remove(resume_path)
        except Exception as e:
            logging.error(f"خطا در حذف فایل رزومه: {e}")

    db.session.delete(profile)
    db.session.commit()
    flash('پروفایل کاریابی شما با موفقیت حذف شد.', 'success')
    return redirect(url_for('main.dashboard'))



@bp.route('/hiring')
def job_listings_page():
    """
    نمایش لیست آگهی‌های استخدام با قابلیت جستجو.
    """

    job_listings = JobListing.query.order_by(JobListing.created_at.desc()).all()
    
    return render_template('job_listings.html',
                           job_listings=job_listings,
                           CooperationType=CooperationType,
                           SalaryType=SalaryType
                           )


@bp.route('/seekers')
def job_seekers_page():
    """
    نمایش لیست پروفایل‌های کاریابی با قابلیت جستجو.
    """
    job_profiles = JobProfile.query.order_by(JobProfile.created_at.desc()).all()
    
    return render_template('job_seekers.html',
                           job_profiles=job_profiles,
                           EducationLevel=EducationLevel,
                           MaritalStatus=MaritalStatus,
                           MilitaryStatus=MilitaryStatus
                           )


@bp.route('/job-listing/<int:job_id>')
def job_listing_detail(job_id):
    """
    نمایش جزئیات یک آگهی استخدام خاص.
    """
    job = JobListing.query.get_or_404(job_id)
    already_applied = False
    if current_user.is_authenticated and current_user.job_profile:
        if job in current_user.job_profile.applied_to_listings.all():
            already_applied = True

    return render_template('job_listing_detail.html', job=job, already_applied=already_applied)


@bp.route('/job-profile/<int:profile_id>')
def job_profile_detail(profile_id):
    """
    نمایش جزئیات یک پروفایل کاریابی خاص.
    """
    profile = JobProfile.query.get_or_404(profile_id)
    work_experiences = profile.work_experiences.order_by(WorkExperience.start_date.desc()).all()
    return render_template('job_profile_detail.html', profile=profile, work_experiences=work_experiences)





@bp.route('/job-profile/edit/summary', methods=['POST'])
@login_required
def edit_job_profile_summary():
    """
    روت AJAX برای ویرایش سریع عنوان و توضیحات پروفایل کاریابی.
    """
    profile = JobProfile.query.filter_by(user_id=current_user.id).first_or_404()
    data = request.get_json()

    if 'title' in data and 'description' in data:
        profile.title = data['title']
        profile.description = data['description']
        db.session.commit()
        return jsonify({
            'success': True, 
            'message': 'اطلاعات با موفقیت به‌روزرسانی شد.',
            'new_title': profile.title,
            'new_description': profile.description
        })
    
    return jsonify({'success': False, 'message': 'اطلاعات ارسالی ناقص است.'}), 400



@bp.route('/job-profile/edit/contact', methods=['POST'])
@login_required
def edit_job_profile_contact():
    profile = JobProfile.query.filter_by(user_id=current_user.id).first_or_404()
    data = request.get_json()
    try:
        profile.contact_phone = data.get('contact_phone')
        profile.contact_email = data.get('contact_email')
        profile.location = data.get('location')
        birth_date_str = data.get('birth_date')
        logging.debug(f"Received birth_date: {birth_date_str}")
        profile.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date() if birth_date_str else None
        profile.marital_status = MaritalStatus[data.get('marital_status')] if data.get('marital_status') else None
        profile.military_status = MilitaryStatus[data.get('military_status')] if data.get('military_status') else None
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'اطلاعات تماس و فردی با موفقیت به‌روزرسانی شد.',
            'new_data': {
                'phone': profile.contact_phone,
                'email': profile.contact_email or 'ثبت نشده',
                'location': profile.location or 'ثبت نشده',
                'birth_date': profile.birth_date.strftime('%Y-%m-%d') if profile.birth_date else 'ثبت نشده',
                'marital_status': profile.marital_status.value if profile.marital_status else 'ثبت نشده',
                'military_status': profile.military_status.value if profile.military_status else 'ثبت نشده'
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'خطا: {e}'}), 400


@bp.route('/job-profile/edit/education', methods=['POST'])
@login_required
def edit_job_profile_education():
    profile = JobProfile.query.filter_by(user_id=current_user.id).first_or_404()
    data = request.get_json()
    try:
        profile.highest_education_level = EducationLevel[data.get('highest_education_level')] if data.get('highest_education_level') else None
        profile.education_status = data.get('education_status')
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'اطلاعات تحصیلی با موفقیت به‌روزرسانی شد.',
            'new_data': {
                'level': profile.highest_education_level.value if profile.highest_education_level else 'ثبت نشده',
                'status': profile.education_status or 'ثبت نشده'
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'خطا: {e}'}), 400


@bp.route('/job-profile/edit/picture', methods=['POST'])
@login_required
def edit_job_profile_picture():
    profile = JobProfile.query.filter_by(user_id=current_user.id).first_or_404()
    data = request.get_json()
    new_path = data.get('image_path')
    if new_path:
        profile.profile_picture = new_path
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'عکس پروفایل با موفقیت تغییر کرد.',
            'new_path': url_for('static', filename=f'uploads/{new_path}')
        })
    return jsonify({'success': False, 'message': 'مسیر عکسی ارسال نشده است.'}), 400


@bp.route('/apply/<int:job_listing_id>', methods=['POST'])
@login_required
def apply_to_job(job_listing_id):
    job_listing = JobListing.query.get_or_404(job_listing_id)
    job_seeker_profile = current_user.job_profile

    if not job_seeker_profile:
        flash('برای ارسال رزومه، ابتدا باید پروفایل کاریابی خود را بسازید.', 'warning')
        return redirect(url_for('main.new_job_profile'))

    if job_listing in job_seeker_profile.applied_to_listings:
        flash('شما قبلاً برای این آگهی رزومه ارسال کرده‌اید.', 'info')
        return redirect(url_for('main.job_listing_detail', job_id=job_listing_id))

    job_seeker_profile.applied_to_listings.append(job_listing)
    db.session.commit()

    flash('رزومه شما با موفقیت برای این آگهی ارسال شد.', 'success')
    return redirect(url_for('main.job_listing_detail', job_id=job_listing_id))


@bp.route('/job-listing/<int:job_listing_id>/applications')
@login_required
def view_job_applications(job_listing_id):
    job_listing = JobListing.query.get_or_404(job_listing_id)

    if job_listing.owner != current_user and not current_user.is_admin:
        abort(403)

    applicants = job_listing.applicants.order_by(job_applications.c.application_date.desc()).all()

    return render_template('job_applications.html', job_listing=job_listing, applicants=applicants)



@bp.route('/report_job_listing/<int:job_listing_id>', methods=['POST'])
@login_required
def report_job_listing(job_listing_id):
    job_listing = JobListing.query.get_or_404(job_listing_id)
    report_reason = request.form.get('report_reason')

    if not report_reason:
        flash('دلیل گزارش نمی‌تواند خالی باشد.', 'danger')
        return redirect(url_for('main.job_listing_detail', job_id=job_listing_id))

    if job_listing.user_id == current_user.id:
        flash('شما نمی‌توانید آگهی خود را گزارش دهید.', 'warning')
        return redirect(url_for('main.job_listing_detail', job_id=job_listing_id))

    report = JobListingReport(
        job_listing_id=job_listing_id,
        reporter_id=current_user.id,
        reason=report_reason
    )
    db.session.add(report)
    db.session.commit()
    flash('آگهی استخدام با موفقیت گزارش شد و توسط مدیران بررسی خواهد شد.', 'success')
    return redirect(url_for('main.job_listing_detail', job_id=job_listing_id))


@bp.route('/report_job_profile/<int:job_profile_id>', methods=['POST'])
@login_required
def report_job_profile(job_profile_id):
    job_profile = JobProfile.query.get_or_404(job_profile_id)
    report_reason = request.form.get('report_reason')

    if not report_reason:
        flash('دلیل گزارش نمی‌تواند خالی باشد.', 'danger')
        return redirect(url_for('main.job_profile_detail', profile_id=job_profile_id))

    if job_profile.user_id == current_user.id:
        flash('شما نمی‌توانید پروفایل خود را گزارش دهید.', 'warning')
        return redirect(url_for('main.job_profile_detail', profile_id=job_profile_id))
        
    report = JobProfileReport(
        job_profile_id=job_profile_id,
        reporter_id=current_user.id,
        reason=report_reason
    )
    db.session.add(report)
    db.session.commit()
    flash('پروفایل کاریابی با موفقیت گزارش شد و توسط مدیران بررسی خواهد شد.', 'success')
    return redirect(url_for('main.job_profile_detail', profile_id=job_profile_id))



@bp.route('/admin/delete_job_listing_report/<int:report_id>', methods=['POST'])
@login_required
def delete_job_listing_report(report_id):
    if not current_user.is_admin:
        flash("شما دسترسی به این بخش را ندارید", "danger")
        return redirect(url_for('main.index'))

    report = JobListingReport.query.get_or_404(report_id)
    db.session.delete(report)
    db.session.commit()
    flash("گزارش آگهی استخدام با موفقیت حذف شد.", "success")
    return redirect(url_for('main.admin_dashboard'))

@bp.route('/admin/delete_job_profile_report/<int:report_id>', methods=['POST'])
@login_required
def delete_job_profile_report(report_id):
    if not current_user.is_admin:
        flash("شما دسترسی به این بخش را ندارید", "danger")
        return redirect(url_for('main.index'))

    report = JobProfileReport.query.get_or_404(report_id)
    db.session.delete(report)
    db.session.commit()
    flash("گزارش پروفایل کاریابی با موفقیت حذف شد.", "success")
    return redirect(url_for('main.admin_dashboard'))



@bp.route('/live_search_jobs')
def live_search_jobs():
    search_term = request.args.get('search', '').strip()
    active_tab = request.args.get('active_tab', 'hiring')

    cooperation_type_filter = request.args.get('cooperation_type_filter')
    salary_type_filter = request.args.get('salary_type_filter')
    has_insurance_filter = request.args.get('has_insurance_filter')
    is_internship_filter = request.args.get('is_internship_filter')

    education_level_filter = request.args.get('education_level_filter')
    education_status_filter = request.args.get('education_status_filter')
    marital_status_filter = request.args.get('marital_status_filter')
    military_status_filter = request.args.get('military_status_filter')

    if active_tab == 'hiring':
        query = JobListing.query
        if search_term:
            search_keywords = search_term.lower().split()
            conditions = []
            for kw in search_keywords:
                conditions.append(JobListing.title.ilike(f'%{kw}%'))
                conditions.append(JobListing.description.ilike(f'%{kw}%'))
                conditions.append(JobListing.benefits.ilike(f'%{kw}%'))
                conditions.append(JobListing.working_hours.ilike(f'%{kw}%'))
                conditions.append(JobListing.location.ilike(f'%{kw}%'))
            query = query.filter(db.or_(*conditions))
        
        if cooperation_type_filter:
            try:
                enum_cooperation = CooperationType[cooperation_type_filter]
                query = query.filter(JobListing.cooperation_type == enum_cooperation)
            except KeyError:
                pass
        
        if salary_type_filter:
            try:
                enum_salary = SalaryType[salary_type_filter]
                query = query.filter(JobListing.salary_type == enum_salary)
            except KeyError:
                pass
        
        if has_insurance_filter == 'true':
            query = query.filter(JobListing.has_insurance == True)

        if is_internship_filter == 'true':
            query = query.filter(JobListing.cooperation_type == CooperationType.INTERNSHIP)


        job_listings = query.order_by(JobListing.created_at.desc()).all()
        return render_template('_job_listing_list.html', job_listings=job_listings)

    elif active_tab == 'seekers':
        query = JobProfile.query
        if search_term:
            search_keywords = search_term.lower().split()
            conditions = []
            for kw in search_keywords:
                conditions.append(JobProfile.title.ilike(f'%{kw}%'))
                conditions.append(JobProfile.description.ilike(f'%{kw}%'))
                conditions.append(JobProfile.location.ilike(f'%{kw}%'))
                conditions.append(
                    JobProfile.work_experiences.any(
                        db.or_(
                            WorkExperience.job_title.ilike(f'%{kw}%'),
                            WorkExperience.company_name.ilike(f'%{kw}%')
                        )
                    )
                )
            query = query.filter(db.or_(*conditions))

        if education_level_filter:
            try:
                enum_edu_level = EducationLevel[education_level_filter]
                query = query.filter(JobProfile.highest_education_level == enum_edu_level)
            except KeyError:
                pass

        if education_status_filter:
            query = query.filter(JobProfile.education_status.ilike(f'%{education_status_filter}%'))
        
        if marital_status_filter:
            try:
                enum_marital = MaritalStatus[marital_status_filter]
                query = query.filter(JobProfile.marital_status == enum_marital)
            except KeyError:
                pass

        if military_status_filter:
            try:
                enum_military = MilitaryStatus[military_status_filter]
                query = query.filter(JobProfile.military_status == enum_military)
            except KeyError:
                pass

        job_profiles = query.order_by(JobProfile.created_at.desc()).all()
        return render_template('_job_profile_list.html', job_profiles=job_profiles)
    
    return ""