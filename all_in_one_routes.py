import os
from flask import jsonify, redirect, url_for, flash, request, Blueprint, session, current_app, abort, send_from_directory
from flask_login import login_user, logout_user, login_required, current_user
import traceback
from urllib.parse import urlparse
from aplication import db, limiter
from models import User, Product, Category, EditProfileForm, Message, Conversation, Report, SignupTempData, ChatBotInteraction, ProductType, ProductForm
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import logging
import random
import requests
import re

# ایجاد blueprint برای مسیرها
bp = Blueprint('api', __name__)

logging.basicConfig(level=logging.DEBUG)

# توابع کمکی برای تبدیل اطلاعات به JSON

def format_user(user, include_sensitive=False):
    """تبدیل اطلاعات کاربر به فرمت JSON"""
    data = {
        'id': user.id,
        'username': user.username,
        'joined_at': user.created_at.isoformat() if hasattr(user, 'created_at') and user.created_at else None,
        'bio': user.bio if hasattr(user, 'bio') else None,
        'avatar': user.avatar if hasattr(user, 'avatar') else None,
    }
    
    if include_sensitive and current_user.is_authenticated and current_user.id == user.id:
        data.update({
            'email': user.email if hasattr(user, 'email') else None,
            'phone': user.phone if hasattr(user, 'phone') else None,
            'national_id': user.national_id if hasattr(user, 'national_id') else None,
        })
    
    return data

def format_product(product):
    """تبدیل محصول به فرمت JSON"""
    return {
        'id': product.id,
        'name': product.name,
        'description': product.description,
        'price': product.price,
        'category_id': product.category_id,
        'category_name': product.category.name if product.category else None,
        'image_path': product.image_path,
        'status': product.status,
        'views': product.views,
        'user_id': product.user_id,
        'user_name': product.owner.username if product.owner else None,
        'created_at': product.created_at.isoformat() if product.created_at else None,
        'updated_at': product.updated_at.isoformat() if product.updated_at else None,
        'address': product.address,
        'postal_code': product.postal_code,
        'product_type': product.product_type.value if product.product_type else None,
        'promoted_until': product.promoted_until.isoformat() if product.promoted_until else None,
        'is_promoted': product.is_promoted,
        'expires_at': product.expires_at.isoformat() if product.expires_at else None
    }

def format_category(category):
    """تبدیل دسته‌بندی به فرمت JSON"""
    return {
        'id': category.id,
        'name': category.name,
        'icon': category.icon,
        'parent_id': category.parent_id,
        'subcategories': [format_category(subcat) for subcat in category.subcategories] if hasattr(category, 'subcategories') else []
    }

def format_message(message):
    """تبدیل پیام به فرمت JSON"""
    return {
        'id': message.id,
        'content': message.content,
        'timestamp': message.timestamp.isoformat() if message.timestamp else None,
        'sender_id': message.sender_id,
        'sender_name': message.sender.username if message.sender else None,
        'receiver_id': message.receiver_id,
        'receiver_name': message.receiver.username if message.receiver else None,
        'conversation_id': message.conversation_id,
        'replied_to_id': message.replied_to_id,
        'file_path': message.file_path
    }

def format_conversation(convo):
    """تبدیل مکالمه به فرمت JSON"""
    return {
        'id': convo.id,
        'user1_id': convo.user1_id,
        'user1_name': convo.user1.username if convo.user1 else None,
        'user2_id': convo.user2_id,
        'user2_name': convo.user2.username if convo.user2 else None,
        'last_message': format_message(convo.messages[-1]) if convo.messages and len(convo.messages) > 0 else None
    }

def format_report(report):
    """تبدیل گزارش به فرمت JSON"""
    return {
        'id': report.id,
        'product_id': report.product_id,
        'product_name': report.product.name if report.product else None,
        'reporter_id': report.reporter_id,
        'reporter_name': report.reporter.username if report.reporter else None,
        'text': report.text,
        'created_at': report.created_at.isoformat() if report.created_at else None
    }

def save_image(file, upload_folder='static/uploads'):
    """ذخیره‌سازی تصویر آپلود شده"""
    if not file:
        return None
        
    # ایجاد پوشه در صورت عدم وجود
    os.makedirs(upload_folder, exist_ok=True)
    
    # ایجاد نام فایل امن
    filename = secure_filename(file.filename)
    unique_filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{filename}"
    
    # ذخیره‌سازی فایل
    filepath = os.path.join(upload_folder, unique_filename)
    file.save(filepath)
    
    # بازگرداندن مسیر نسبی
    return os.path.join('uploads', unique_filename)

def send_verification_code(phone, code):
    """ارسال کد تایید به شماره موبایل"""
    # TODO: این تابع باید با سرویس پیامک شما جایگزین شود
    current_app.logger.info(f"Sending verification code {code} to {phone}")
    return True

# مسیرهای API

@bp.route('/')
@limiter.limit("5 per minute")
def index():
    """صفحه اصلی - نمایش محصولات"""
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
            (Product.is_promoted == True, 1),  # اگر نردبان شده، بالاتر قرار بگیرد
            else_=0  # در غیر این صورت، پایین‌تر قرار بگیرد
        ).desc(),  # ترتیب نزولی، یعنی نردبان‌شده‌ها بالاتر باشند
        Product.created_at.desc()  # سپس جدیدترین محصولات بالاتر باشند
    ).all()
    
    # دریافت دسته‌بندی‌ها
    categories = Category.query.filter_by(parent_id=None).all()
    
    # تبدیل به JSON
    return jsonify({
        'products': [format_product(product) for product in products],
        'top_products': [format_product(product) for product in top_products],
        'categories': [format_category(category) for category in categories],
        'provinces': provinces,
        'cities_with_products': cities_with_products,
        'cities_by_province': citiesByProvince
    })

@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    """ورود کاربر به سیستم"""
    if current_user.is_authenticated:
        return jsonify({
            'status': 'success',
            'message': 'شما قبلا وارد شده‌اید',
            'redirect': url_for('main.index')
        })

    if request.method == 'POST':
        # برای درخواست‌های JSON
        if request.is_json:
            data = request.get_json()
            identifier = data.get('username', '').strip()
            password = data.get('password', '')
        else:
            # برای درخواست‌های form-data
            identifier = request.form.get('username', '').strip()
            password = request.form.get('password', '')

        # جستجو با نام کاربری یا شماره تماس
        user = User.query.filter(
            (User.username == identifier) | (User.phone == identifier)
        ).first()

        if user is None or not user.check_password(password):
            return jsonify({
                'status': 'error',
                'message': 'نام کاربری یا رمز عبور نامعتبر است یا اکانت وجود ندارد'
            }), 401

        # شماره‌هایی که نیاز به تأیید پیامکی ندارند
        whitelist_phones = ['09123456789']

        if user.phone in whitelist_phones:
            login_user(user, remember=True)
            return jsonify({
                'status': 'success',
                'message': 'ورود با موفقیت انجام شد!',
                'redirect': url_for('main.index'),
                'user': format_user(user, include_sensitive=True)
            })

        # ارسال OTP به شماره کاربر
        otp = random.randint(1000, 9999)
        session['otp_code'] = otp
        session['user_id'] = user.id

        try:
            send_verification_code(user.phone, otp)
            return jsonify({
                'status': 'verify_needed',
                'message': 'کد تایید به شماره شما ارسال شد',
                'redirect': url_for('main.verify_login')
            })
        except Exception as e:
            current_app.logger.error(f"Error sending verification code: {str(e)}")
            return jsonify({
                'status': 'error',
                'message': 'خطا در ارسال کد تایید'
            }), 500

    # اگر درخواست GET باشد، اطلاعات لازم برای صفحه لاگین را برمی‌گردانیم
    return jsonify({
        'status': 'ready',
        'message': 'لطفا اطلاعات ورود را وارد کنید'
    })

@bp.route('/verify_login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def verify_login():
    """تایید کد ورود پیامکی"""
    if request.method == 'POST':
        # برای درخواست‌های JSON
        if request.is_json:
            data = request.get_json()
            entered_code = data.get('code')
        else:
            # برای درخواست‌های form-data
            entered_code = request.form.get('code')
            
        user_id = session.get('user_id')
        otp_code = session.get('otp_code')

        if not user_id or not otp_code:
            return jsonify({
                'status': 'error',
                'message': 'اطلاعات جلسه ناقص است. لطفاً دوباره وارد شوید.',
                'redirect': url_for('main.login')
            }), 400

        user = User.query.get(user_id)

        if not user:
            return jsonify({
                'status': 'error',
                'message': 'کاربر یافت نشد.',
                'redirect': url_for('main.login')
            }), 404

        # شماره‌های سفید که تاییدیه لازم ندارند:
        whitelist_phones = ['09123456789']

        if user.phone in whitelist_phones:
            current_app.logger.info(f"User {user.phone} is in whitelist, bypassing OTP.")
        elif entered_code != str(otp_code):
            return jsonify({
                'status': 'error',
                'message': 'کد وارد شده اشتباه است!'
            }), 400

        # لاگین موفق
        login_user(user, remember=True)
        current_app.logger.info(f"User {user.phone} logged in successfully.")

        # پاک کردن سشن‌ها
        session.pop('otp_code', None)
        session.pop('user_id', None)

        return jsonify({
            'status': 'success',
            'message': 'ورود با موفقیت انجام شد!',
            'redirect': url_for('main.index'),
            'user': format_user(user, include_sensitive=True)
        })

    # اگر درخواست GET باشد
    return jsonify({
        'status': 'waiting_verification',
        'message': 'لطفا کد تایید دریافتی را وارد کنید'
    })

@bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """خروج کاربر از سیستم"""
    logout_user()
    return jsonify({
        'status': 'success',
        'message': 'خروج با موفقیت انجام شد',
        'redirect': url_for('main.index')
    })

@bp.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    """داشبورد کاربر"""
    if request.method == 'GET':
        user = current_user
        products = Product.query.filter_by(user_id=user.id).all()
        return jsonify({
            'status': 'success',
            'user': format_user(user, include_sensitive=True),
            'products': [format_product(product) for product in products]
        })
    else:  # POST - ویرایش پروفایل
        form = EditProfileForm(
            username=request.form.get('username'),
            email=request.form.get('email'),
            phone=request.form.get('phone')
        )
        
        if form.validate_on_submit():
            # بررسی یکتا بودن نام کاربری و ایمیل
            username_exists = User.query.filter(User.username == form.username and User.id != current_user.id).first()
            email_exists = User.query.filter(User.email == form.email and User.id != current_user.id).first()
            phone_exists = User.query.filter(User.phone == form.phone and User.id != current_user.id).first()
            
            if username_exists:
                return jsonify({
                    'status': 'error',
                    'message': 'این نام کاربری قبلا استفاده شده است'
                }), 400
            
            if email_exists:
                return jsonify({
                    'status': 'error',
                    'message': 'این ایمیل قبلا استفاده شده است'
                }), 400
                
            if phone_exists:
                return jsonify({
                    'status': 'error',
                    'message': 'این شماره تلفن قبلا استفاده شده است'
                }), 400
            
            # اعمال تغییرات
            if form.username:
                current_user.username = form.username
            if form.email:
                current_user.email = form.email
                
            # اگر شماره تلفن تغییر کرده باشد، باید تایید شود
            if form.phone and form.phone != current_user.phone:
                # ایجاد کد تایید
                verification_code = str(random.randint(1000, 9999))
                session['verification_code'] = verification_code
                session['new_phone'] = form.phone
                
                # ارسال کد تایید
                try:
                    send_verification_code(form.phone, verification_code)
                    return jsonify({
                        'status': 'verification_needed',
                        'message': 'کد تایید به شماره جدید ارسال شد.',
                        'redirect': url_for('main.verify_phone_change')
                    })
                except Exception as e:
                    current_app.logger.error(f"Error sending verification code: {str(e)}")
                    return jsonify({
                        'status': 'error',
                        'message': 'خطا در ارسال کد تایید'
                    }), 500
                    
            # ذخیره تغییرات
            db.session.commit()
            
            return jsonify({
                'status': 'success',
                'message': 'پروفایل با موفقیت به‌روزرسانی شد',
                'user': format_user(current_user, include_sensitive=True)
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'داده‌های ارسالی معتبر نیستند',
                'errors': form.errors
            }), 400

@bp.route('/verify-phone-change', methods=['GET', 'POST'])
@login_required
def verify_phone_change():
    """تایید تغییر شماره تلفن"""
    if request.method == 'POST':
        # برای درخواست‌های JSON
        if request.is_json:
            data = request.get_json()
            entered_code = data.get('code')
        else:
            # برای درخواست‌های form-data
            entered_code = request.form.get('code')
            
        verification_code = session.get('verification_code')
        new_phone = session.get('new_phone')
        
        if not verification_code or not new_phone:
            return jsonify({
                'status': 'error',
                'message': 'اطلاعات جلسه ناقص است. لطفاً دوباره تلاش کنید.',
                'redirect': url_for('main.dashboard')
            }), 400
            
        if entered_code != verification_code:
            return jsonify({
                'status': 'error',
                'message': 'کد وارد شده اشتباه است.'
            }), 400
            
        # تغییر شماره تلفن
        current_user.phone = new_phone
        db.session.commit()
        
        # پاک کردن سشن‌ها
        session.pop('verification_code', None)
        session.pop('new_phone', None)
        
        return jsonify({
            'status': 'success',
            'message': 'شماره تلفن با موفقیت تغییر یافت.',
            'redirect': url_for('main.dashboard'),
            'user': format_user(current_user, include_sensitive=True)
        })
        
    # اگر درخواست GET باشد
    return jsonify({
        'status': 'waiting_verification',
        'message': 'لطفا کد تایید دریافتی را وارد کنید',
        'new_phone': session.get('new_phone')
    })

@bp.route('/renew_product/<int:product_id>', methods=['POST'])
@login_required
def renew_product(product_id):
    """تمدید آگهی محصول"""
    product = Product.query.get_or_404(product_id)
    
    # فقط صاحب محصول می‌تواند آن را تمدید کند
    if current_user.id != product.user_id:
        return jsonify({
            'status': 'error',
            'message': 'شما اجازه تمدید این محصول را ندارید'
        }), 403
        
    # تمدید محصول برای 30 روز دیگر
    product.expires_at = datetime.utcnow() + timedelta(days=30)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'محصول با موفقیت تمدید شد',
        'product': format_product(product)
    })

@bp.route('/user_dashboard/<int:user_id>')
def user_dashboard(user_id):
    """مشاهده پروفایل و محصولات کاربر دیگر"""
    user = User.query.get_or_404(user_id)
    products = Product.query.filter_by(user_id=user.id, status='published').all()
    
    return jsonify({
        'status': 'success',
        'user': format_user(user, include_sensitive=False),
        'products': [format_product(product) for product in products]
    })

@bp.route('/products/new', methods=['GET', 'POST'])
@login_required
def new_product():
    """ایجاد محصول جدید"""
    if request.method == 'POST':
        # برای درخواست‌های JSON
        if request.is_json:
            data = request.get_json()
            name = data.get('name', '').strip()
            description = data.get('description', '').strip()
            price = data.get('price')
            category_id = data.get('category_id')
            address = data.get('address', '').strip()
            postal_code = data.get('postal_code', '').strip()
            product_type = data.get('product_type')
            # توجه: آپلود فایل در JSON امکان‌پذیر نیست و باید از form-data استفاده شود
            image_path = None
        else:
            # برای درخواست‌های form-data
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            price = request.form.get('price')
            category_id = request.form.get('category_id')
            address = request.form.get('address', '').strip()
            postal_code = request.form.get('postal_code', '').strip()
            product_type = request.form.get('product_type')
            
            # آپلود تصویر
            image = request.files.get('image')
            image_path = save_image(image) if image else None
        
        # بررسی اعتبار داده‌ها
        errors = {}
        
        if not name:
            errors['name'] = 'نام محصول الزامی است'
            
        if not description:
            errors['description'] = 'توضیحات محصول الزامی است'
            
        if not price:
            errors['price'] = 'قیمت محصول الزامی است'
        else:
            try:
                price = float(price)
            except ValueError:
                errors['price'] = 'قیمت باید عدد باشد'
                
        if not category_id:
            errors['category_id'] = 'دسته‌بندی الزامی است'
        else:
            category = Category.query.get(category_id)
            if not category:
                errors['category_id'] = 'دسته‌بندی نامعتبر است'
                
        if not address:
            errors['address'] = 'آدرس الزامی است'
            
        if not postal_code:
            errors['postal_code'] = 'کد پستی الزامی است'
            
        if not product_type:
            errors['product_type'] = 'نوع محصول الزامی است'
        else:
            try:
                # تبدیل رشته به enum
                product_type = ProductType[product_type]
            except KeyError:
                errors['product_type'] = 'نوع محصول نامعتبر است'
            
        if request.is_json and not 'image_path' in data:
            errors['image'] = 'برای آپلود تصویر باید از form-data استفاده کنید'
        elif not request.is_json and not image_path:
            errors['image'] = 'تصویر محصول الزامی است'
            
        if errors:
            return jsonify({
                'status': 'error',
                'message': 'لطفاً خطاهای زیر را برطرف کنید',
                'errors': errors
            }), 400
            
        # ایجاد محصول جدید
        product = Product(
            name=name,
            description=description,
            price=price,
            image_path=image_path,
            user_id=current_user.id,
            category_id=category_id,
            address=address,
            postal_code=postal_code,
            product_type=product_type,
            status='pending',  # محصول ابتدا در وضعیت بررسی قرار می‌گیرد
            expires_at=datetime.utcnow() + timedelta(days=30)  # محصول 30 روز اعتبار دارد
        )
        
        db.session.add(product)
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'محصول با موفقیت ثبت شد و در انتظار تایید است',
            'product': format_product(product),
            'redirect': url_for('main.product_detail', product_id=product.id)
        })
    
    # اگر درخواست GET باشد، لیست دسته‌بندی‌ها و انواع محصول را برمی‌گردانیم
    categories = Category.query.all()
    product_types = [{"name": pt.name, "value": pt.value} for pt in ProductType]
    
    return jsonify({
        'status': 'ready',
        'message': 'لطفا اطلاعات محصول را وارد کنید',
        'categories': [format_category(category) for category in categories],
        'product_types': product_types
    })

@bp.route('/products/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_product(id):
    """ویرایش محصول"""
    product = Product.query.get_or_404(id)
    
    # فقط صاحب محصول یا ادمین می‌تواند محصول را ویرایش کند
    if current_user.id != product.user_id and not current_user.is_admin:
        return jsonify({
            'status': 'error',
            'message': 'شما اجازه ویرایش این محصول را ندارید'
        }), 403
    
    if request.method == 'POST':
        # برای درخواست‌های JSON
        if request.is_json:
            data = request.get_json()
            name = data.get('name', '').strip()
            description = data.get('description', '').strip()
            price = data.get('price')
            category_id = data.get('category_id')
            address = data.get('address', '').strip()
            postal_code = data.get('postal_code', '').strip()
            product_type = data.get('product_type')
        else:
            # برای درخواست‌های form-data
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            price = request.form.get('price')
            category_id = request.form.get('category_id')
            address = request.form.get('address', '').strip()
            postal_code = request.form.get('postal_code', '').strip()
            product_type = request.form.get('product_type')
            
            # آپلود تصویر جدید اگر وجود داشته باشد
            image = request.files.get('image')
            if image:
                new_image_path = save_image(image)
                if new_image_path:
                    product.image_path = new_image_path
        
        # بررسی اعتبار داده‌ها
        errors = {}
        
        if not name:
            errors['name'] = 'نام محصول الزامی است'
            
        if not description:
            errors['description'] = 'توضیحات محصول الزامی است'
            
        if not price:
            errors['price'] = 'قیمت محصول الزامی است'
        else:
            try:
                price = float(price)
            except ValueError:
                errors['price'] = 'قیمت باید عدد باشد'
                
        if not category_id:
            errors['category_id'] = 'دسته‌بندی الزامی است'
        else:
            category = Category.query.get(category_id)
            if not category:
                errors['category_id'] = 'دسته‌بندی نامعتبر است'
                
        if not address:
            errors['address'] = 'آدرس الزامی است'
            
        if not postal_code:
            errors['postal_code'] = 'کد پستی الزامی است'
            
        if product_type:
            try:
                # تبدیل رشته به enum
                product_type = ProductType[product_type]
            except KeyError:
                errors['product_type'] = 'نوع محصول نامعتبر است'
                
        if errors:
            return jsonify({
                'status': 'error',
                'message': 'لطفاً خطاهای زیر را برطرف کنید',
                'errors': errors
            }), 400
            
        # به‌روزرسانی محصول
        if name:
            product.name = name
        if description:
            product.description = description
        if price:
            product.price = price
        if category_id:
            product.category_id = category_id
        if address:
            product.address = address
        if postal_code:
            product.postal_code = postal_code
        if product_type:
            product.product_type = product_type
            
        product.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'محصول با موفقیت ویرایش شد',
            'product': format_product(product),
            'redirect': url_for('main.product_detail', product_id=product.id)
        })
    
    # اگر درخواست GET باشد، اطلاعات محصول و لیست دسته‌بندی‌ها را برمی‌گردانیم
    categories = Category.query.all()
    product_types = [{"name": pt.name, "value": pt.value} for pt in ProductType]
    
    return jsonify({
        'status': 'ready',
        'message': 'لطفا اطلاعات محصول را ویرایش کنید',
        'product': format_product(product),
        'categories': [format_category(category) for category in categories],
        'product_types': product_types
    })

@bp.route('/products/<int:id>/delete', methods=['POST'])
@login_required
def delete_product(id):
    """حذف محصول"""
    product = Product.query.get_or_404(id)
    
    # فقط صاحب محصول یا ادمین می‌تواند محصول را حذف کند
    if current_user.id != product.user_id and not current_user.is_admin:
        return jsonify({
            'status': 'error',
            'message': 'شما اجازه حذف این محصول را ندارید'
        }), 403
    
    db.session.delete(product)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'محصول با موفقیت حذف شد',
        'redirect': url_for('main.dashboard')
    })

@bp.route('/products/<int:product_id>')
def product_detail(product_id):
    """نمایش جزئیات محصول"""
    product = Product.query.get_or_404(product_id)
    
    # افزایش تعداد بازدید
    if not current_user.is_authenticated or current_user.id != product.user_id:
        product.views += 1
        db.session.commit()
    
    # دریافت دسته‌بندی‌ها برای نمایش در سایدبار
    categories = Category.query.all()
    
    # نمایش شماره تماس فروشنده فقط به کاربران لاگین شده
    phone = None
    if current_user.is_authenticated:
        phone = product.owner.phone if product.owner else None
    
    return jsonify({
        'status': 'success',
        'product': format_product(product),
        'seller': format_user(product.owner, include_sensitive=False) if product.owner else None,
        'categories': [format_category(category) for category in categories],
        'phone': phone
    })

@bp.route('/init-categories', methods=['POST'])
@login_required
def init_categories():
    """ایجاد دسته‌بندی‌های پیش‌فرض (فقط برای ادمین)"""
    if not current_user.is_admin:
        return jsonify({
            'status': 'error',
            'message': 'فقط ادمین می‌تواند این عملیات را انجام دهد'
        }), 403
    
    # لیست دسته‌بندی‌ها
    categories = [
        {'name': 'املاک', 'icon': 'home'},
        {'name': 'وسایل نقلیه', 'icon': 'car'},
        {'name': 'کالای دیجیتال', 'icon': 'smartphone'},
        {'name': 'خانه و آشپزخانه', 'icon': 'refrigerator'},
        {'name': 'خدمات', 'icon': 'tools'},
        {'name': 'وسایل شخصی', 'icon': 'watch'},
        {'name': 'سرگرمی و فراغت', 'icon': 'gamepad'},
        {'name': 'اجتماعی', 'icon': 'users'},
        {'name': 'تجهیزات و صنعتی', 'icon': 'factory'},
        {'name': 'استخدام و کاریابی', 'icon': 'briefcase'}
    ]
    
    # ایجاد دسته‌بندی‌ها
    for category_data in categories:
        category = Category(name=category_data['name'], icon=category_data['icon'])
        db.session.add(category)
    
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'دسته‌بندی‌های پیش‌فرض با موفقیت ایجاد شدند',
        'categories': [format_category(category) for category in Category.query.all()]
    })

@bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """ثبت نام کاربر جدید"""
    if current_user.is_authenticated:
        return jsonify({
            'status': 'error',
            'message': 'شما قبلا وارد سیستم شده‌اید',
            'redirect': url_for('main.index')
        })

    if request.method == 'POST':
        # برای درخواست‌های JSON
        if request.is_json:
            data = request.get_json()
            username = data.get('username', '').strip()
            email = data.get('email', '').strip()
            phone = data.get('phone', '').strip()
            national_id = data.get('national_id', '').strip()
            password = data.get('password', '')
            password_confirm = data.get('password_confirm', '')
        else:
            # برای درخواست‌های form-data
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone', '').strip()
            national_id = request.form.get('national_id', '').strip()
            password = request.form.get('password', '')
            password_confirm = request.form.get('password_confirm', '')

        # بررسی اعتبار داده‌ها
        errors = {}
        
        # بررسی نام کاربری
        if not username:
            errors['username'] = 'نام کاربری الزامی است'
        elif len(username) < 3:
            errors['username'] = 'نام کاربری باید حداقل ۳ کاراکتر باشد'
        elif User.query.filter_by(username=username).first():
            errors['username'] = 'این نام کاربری قبلاً استفاده شده است'
            
        # بررسی ایمیل
        if not email:
            errors['email'] = 'ایمیل الزامی است'
        elif not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', email):
            errors['email'] = 'فرمت ایمیل صحیح نیست'
        elif User.query.filter_by(email=email).first():
            errors['email'] = 'این ایمیل قبلاً ثبت شده است'
            
        # بررسی شماره موبایل
        if not phone:
            errors['phone'] = 'شماره موبایل الزامی است'
        elif not re.match(r'^09\d{9}$', phone):
            errors['phone'] = 'فرمت شماره موبایل صحیح نیست (مثال: ۰۹۱۲۳۴۵۶۷۸۹)'
        elif User.query.filter_by(phone=phone).first():
            errors['phone'] = 'این شماره موبایل قبلاً ثبت شده است'
            
        # بررسی کد ملی
        if not national_id:
            errors['national_id'] = 'کد ملی الزامی است'
        elif not re.match(r'^\d{10}$', national_id):
            errors['national_id'] = 'کد ملی باید ۱۰ رقم باشد'
        elif User.query.filter_by(national_id=national_id).first():
            errors['national_id'] = 'این کد ملی قبلاً ثبت شده است'
            
        # بررسی رمز عبور
        if not password:
            errors['password'] = 'رمز عبور الزامی است'
        elif len(password) < 6:
            errors['password'] = 'رمز عبور باید حداقل ۶ کاراکتر باشد'
        elif password != password_confirm:
            errors['password_confirm'] = 'تکرار رمز عبور مطابقت ندارد'
            
        if errors:
            return jsonify({
                'status': 'error',
                'message': 'لطفاً خطاهای زیر را برطرف کنید',
                'errors': errors
            }), 400
            
        # ارسال کد تایید به کاربر
        verification_code = str(random.randint(1000, 9999))
        expiration_time = datetime.utcnow() + timedelta(minutes=2)
        
        # ذخیره اطلاعات موقت کاربر
        temp_data = SignupTempData(
            phone=phone,
            code=verification_code,
            expires_at=expiration_time
        )
        
        # ذخیره سایر اطلاعات در session
        session['signup_username'] = username
        session['signup_email'] = email
        session['signup_national_id'] = national_id
        session['signup_password'] = password
        
        db.session.add(temp_data)
        db.session.commit()
        
        try:
            send_verification_code(phone, verification_code)
            return jsonify({
                'status': 'verify_needed',
                'message': 'کد تایید به شماره موبایل شما ارسال شد',
                'redirect': url_for('main.verify')
            })
        except Exception as e:
            current_app.logger.error(f"Error sending verification code: {str(e)}")
            return jsonify({
                'status': 'error',
                'message': 'خطا در ارسال کد تایید'
            }), 500
            
    # اگر درخواست GET باشد
    return jsonify({
        'status': 'ready',
        'message': 'لطفا اطلاعات ثبت نام را وارد کنید'
    })

@bp.route('/verify', methods=['GET', 'POST'])
def verify():
    """تایید کد ثبت نام پیامکی"""
    if request.method == 'POST':
        # برای درخواست‌های JSON
        if request.is_json:
            data = request.get_json()
            entered_code = data.get('code')
        else:
            # برای درخواست‌های form-data
            entered_code = request.form.get('code')
            
        phone = session.get('signup_phone')
        if not phone:
            # اگر شماره تلفن در session نیست، از request استفاده می‌کنیم
            phone = request.form.get('phone') or (request.get_json().get('phone') if request.is_json else None)
            
        if not phone:
            return jsonify({
                'status': 'error',
                'message': 'شماره تلفن یافت نشد',
                'redirect': url_for('main.signup')
            }), 400
        
        # بررسی کد تایید
        temp_data = SignupTempData.query.filter_by(phone=phone).order_by(SignupTempData.created_at.desc()).first()
        
        if not temp_data:
            return jsonify({
                'status': 'error',
                'message': 'اطلاعات ثبت نام یافت نشد. لطفاً دوباره ثبت نام کنید.',
                'redirect': url_for('main.signup')
            }), 404
            
        if temp_data.is_expired():
            db.session.delete(temp_data)
            db.session.commit()
            return jsonify({
                'status': 'error',
                'message': 'کد تایید منقضی شده است. لطفاً دوباره ثبت نام کنید.',
                'redirect': url_for('main.signup')
            }), 400
            
        if entered_code != temp_data.code:
            return jsonify({
                'status': 'error',
                'message': 'کد وارد شده اشتباه است!'
            }), 400
            
        # دریافت اطلاعات ثبت نام از session
        username = session.get('signup_username')
        email = session.get('signup_email')
        national_id = session.get('signup_national_id')
        password = session.get('signup_password')
        
        # ایجاد کاربر جدید
        user = User(
            username=username,
            email=email,
            phone=phone,
            national_id=national_id
        )
        user.set_password(password)
        
        # ذخیره کاربر جدید
        db.session.add(user)
        db.session.delete(temp_data)
        db.session.commit()
        
        # پاک کردن session
        session.pop('signup_username', None)
        session.pop('signup_email', None)
        session.pop('signup_phone', None)
        session.pop('signup_national_id', None)
        session.pop('signup_password', None)
        
        # ورود کاربر
        login_user(user, remember=True)
        
        return jsonify({
            'status': 'success',
            'message': 'ثبت نام با موفقیت انجام شد!',
            'redirect': url_for('main.index'),
            'user': format_user(user, include_sensitive=True)
        })
        
    # اگر درخواست GET باشد
    return jsonify({
        'status': 'waiting_verification',
        'message': 'لطفا کد تایید دریافتی را وارد کنید',
        'phone': session.get('signup_phone')
    })

@bp.route('/start_payment/<int:product_id>', methods=['POST'])
@login_required
def start_payment(product_id):
    """شروع فرآیند پرداخت برای ارتقای محصول"""
    product = Product.query.get_or_404(product_id)
    
    # فقط صاحب محصول می‌تواند آن را ارتقا دهد
    if current_user.id != product.user_id:
        return jsonify({
            'status': 'error',
            'message': 'شما اجازه ارتقای این محصول را ندارید'
        }), 403
        
    # اگر محصول قبلا ارتقا یافته، نمی‌توان دوباره آن را ارتقا داد
    if product.is_promoted and product.promoted_until and product.promoted_until > datetime.utcnow():
        return jsonify({
            'status': 'error',
            'message': 'این محصول قبلا ارتقا یافته است'
        }), 400
        
    # مبلغ ارتقا (به تومان)
    amount = 10000
    
    # ذخیره اطلاعات پرداخت در session
    session['payment_product_id'] = product.id
    session['payment_amount'] = amount
    
    # TODO: اتصال به درگاه پرداخت واقعی
    # اینجا برای تست، مستقیما به صفحه پرداخت موفق هدایت می‌کنیم
    # در حالت واقعی، باید از callback_url استفاده شود
    
    return jsonify({
        'status': 'success',
        'message': 'در حال انتقال به درگاه پرداخت',
        'payment_url': url_for('main.fake_payment', product_id=product.id, amount=amount),
        'amount': amount
    })

@bp.route('/payment_callback', methods=['GET', 'POST'])
def payment_callback():
    """بازگشت از درگاه پرداخت"""
    # دریافت اطلاعات پرداخت از پارامترها یا session
    product_id = request.args.get('product_id') or session.get('payment_product_id')
    amount = request.args.get('amount') or session.get('payment_amount')
    status = request.args.get('status') or 'success'  # در حالت تست، همیشه موفق
    
    if not product_id:
        return jsonify({
            'status': 'error',
            'message': 'اطلاعات پرداخت ناقص است',
            'redirect': url_for('main.index')
        }), 400
        
    product = Product.query.get_or_404(product_id)
    
    # بررسی وضعیت پرداخت
    if status == 'success':
        # ارتقای محصول برای 30 روز
        product.promoted_until = datetime.utcnow() + timedelta(days=30)
        product.is_promoted = True
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'پرداخت با موفقیت انجام شد و محصول شما ارتقا یافت',
            'product': format_product(product),
            'redirect': url_for('main.product_detail', product_id=product.id)
        })
    else:
        return jsonify({
            'status': 'error',
            'message': 'پرداخت ناموفق بود',
            'redirect': url_for('main.product_detail', product_id=product.id)
        }), 400

@bp.route('/promote_product/<int:product_id>', methods=['POST'])
@login_required
def promote_product(product_id):
    """ارتقای محصول (نردبان) به صورت دستی - فقط برای ادمین"""
    if not current_user.is_admin:
        return jsonify({
            'status': 'error',
            'message': 'فقط ادمین می‌تواند این عملیات را انجام دهد'
        }), 403
        
    product = Product.query.get_or_404(product_id)
    
    # ارتقای محصول برای 30 روز
    product.promoted_until = datetime.utcnow() + timedelta(days=30)
    product.is_promoted = True
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'محصول با موفقیت ارتقا یافت',
        'product': format_product(product)
    })

@bp.route('/remove_promotion/<int:product_id>', methods=['POST'])
@login_required
def remove_promotion(product_id):
    """حذف ارتقای محصول (نردبان) به صورت دستی - فقط برای ادمین"""
    if not current_user.is_admin:
        return jsonify({
            'status': 'error',
            'message': 'فقط ادمین می‌تواند این عملیات را انجام دهد'
        }), 403
        
    product = Product.query.get_or_404(product_id)
    
    # حذف ارتقای محصول
    product.promoted_until = None
    product.is_promoted = False
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'ارتقای محصول با موفقیت حذف شد',
        'product': format_product(product)
    })

@bp.route('/admin_dashboard')
@login_required
def admin_dashboard():
    """داشبورد ادمین"""
    if not current_user.is_admin:
        return jsonify({
            'status': 'error',
            'message': 'فقط ادمین می‌تواند به این صفحه دسترسی داشته باشد'
        }), 403
        
    # محصولات در انتظار تأیید
    pending_products = Product.query.filter_by(status='pending').all()
    
    # کاربران
    users = User.query.all()
    
    # گزارش‌های تخلف
    reports = Report.query.all()
    
    return jsonify({
        'status': 'success',
        'pending_products': [format_product(product) for product in pending_products],
        'users': [format_user(user) for user in users],
        'reports': [format_report(report) for report in reports]
    })

@bp.route('/approve_product/<int:product_id>', methods=['POST'])
@login_required
def approve_product(product_id):
    """تأیید محصول - فقط برای ادمین"""
    if not current_user.is_admin:
        return jsonify({
            'status': 'error',
            'message': 'فقط ادمین می‌تواند این عملیات را انجام دهد'
        }), 403
        
    product = Product.query.get_or_404(product_id)
    
    # تأیید محصول
    product.status = 'published'
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'محصول با موفقیت تأیید شد',
        'product': format_product(product)
    })

@bp.route('/report_violation/<int:product_id>', methods=['GET', 'POST'])
@login_required
def report_violation(product_id):
    """گزارش تخلف محصول"""
    product = Product.query.get_or_404(product_id)
    
    if request.method == 'POST':
        # برای درخواست‌های JSON
        if request.is_json:
            data = request.get_json()
            text = data.get('text', '').strip()
        else:
            # برای درخواست‌های form-data
            text = request.form.get('text', '').strip()
            
        if not text:
            return jsonify({
                'status': 'error',
                'message': 'متن گزارش الزامی است'
            }), 400
            
        # بررسی گزارش تکراری
        existing_report = Report.query.filter_by(
            product_id=product.id,
            reporter_id=current_user.id
        ).first()
        
        if existing_report:
            return jsonify({
                'status': 'error',
                'message': 'شما قبلا این محصول را گزارش کرده‌اید'
            }), 400
            
        # ایجاد گزارش جدید
        report = Report(
            product_id=product.id,
            reporter_id=current_user.id,
            text=text
        )
        
        db.session.add(report)
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'گزارش با موفقیت ثبت شد',
            'report': format_report(report)
        })
    
    # اگر درخواست GET باشد
    return jsonify({
        'status': 'ready',
        'message': 'لطفا متن گزارش را وارد کنید',
        'product': format_product(product)
    })

@bp.route('/delete_report/<int:report_id>', methods=['POST'])
@login_required
def delete_report(report_id):
    """حذف گزارش - فقط برای ادمین"""
    if not current_user.is_admin:
        return jsonify({
            'status': 'error',
            'message': 'فقط ادمین می‌تواند این عملیات را انجام دهد'
        }), 403
        
    report = Report.query.get_or_404(report_id)
    
    db.session.delete(report)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'گزارش با موفقیت حذف شد'
    })

@bp.route('/make_admin/<int:user_id>', methods=['POST'])
@login_required
def make_admin(user_id):
    """ارتقای کاربر به ادمین - فقط برای ادمین"""
    if not current_user.is_admin:
        return jsonify({
            'status': 'error',
            'message': 'فقط ادمین می‌تواند این عملیات را انجام دهد'
        }), 403
        
    user = User.query.get_or_404(user_id)
    
    user.is_admin = True
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': f'کاربر {user.username} به ادمین ارتقا یافت',
        'user': format_user(user)
    })

@bp.route('/remove_admin/<int:user_id>', methods=['POST'])
@login_required
def remove_admin(user_id):
    """حذف دسترسی ادمین از کاربر - فقط برای ادمین"""
    if not current_user.is_admin:
        return jsonify({
            'status': 'error',
            'message': 'فقط ادمین می‌تواند این عملیات را انجام دهد'
        }), 403
        
    user = User.query.get_or_404(user_id)
    
    # اگر آخرین ادمین باشد، نمی‌توان دسترسی را حذف کرد
    admin_count = User.query.filter_by(is_admin=True).count()
    if admin_count <= 1 and user.is_admin:
        return jsonify({
            'status': 'error',
            'message': 'باید حداقل یک ادمین وجود داشته باشد'
        }), 400
        
    user.is_admin = False
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': f'دسترسی ادمین از کاربر {user.username} حذف شد',
        'user': format_user(user)
    })

@bp.route('/add_category', methods=['POST'])
@login_required
def add_category():
    """افزودن دسته‌بندی جدید - فقط برای ادمین"""
    if not current_user.is_admin:
        return jsonify({
            'status': 'error',
            'message': 'فقط ادمین می‌تواند این عملیات را انجام دهد'
        }), 403
        
    # برای درخواست‌های JSON
    if request.is_json:
        data = request.get_json()
        name = data.get('name', '').strip()
        icon = data.get('icon', '').strip()
        parent_id = data.get('parent_id')
    else:
        # برای درخواست‌های form-data
        name = request.form.get('name', '').strip()
        icon = request.form.get('icon', '').strip()
        parent_id = request.form.get('parent_id')
        
    if not name:
        return jsonify({
            'status': 'error',
            'message': 'نام دسته‌بندی الزامی است'
        }), 400
        
    # بررسی تکراری بودن نام
    existing_category = Category.query.filter_by(name=name).first()
    if existing_category:
        return jsonify({
            'status': 'error',
            'message': 'این نام دسته‌بندی قبلا استفاده شده است'
        }), 400
        
    # بررسی وجود دسته‌بندی والد
    if parent_id:
        parent = Category.query.get(parent_id)
        if not parent:
            return jsonify({
                'status': 'error',
                'message': 'دسته‌بندی والد یافت نشد'
            }), 400
        
    # ایجاد دسته‌بندی جدید
    category = Category(name=name, icon=icon, parent_id=parent_id)
    db.session.add(category)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'دسته‌بندی با موفقیت ایجاد شد',
        'category': format_category(category)
    })

@bp.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    """حذف کاربر - فقط برای ادمین"""
    if not current_user.is_admin:
        return jsonify({
            'status': 'error',
            'message': 'فقط ادمین می‌تواند این عملیات را انجام دهد'
        }), 403
        
    user = User.query.get_or_404(user_id)
    
    # اگر آخرین ادمین باشد، نمی‌توان آن را حذف کرد
    admin_count = User.query.filter_by(is_admin=True).count()
    if admin_count <= 1 and user.is_admin:
        return jsonify({
            'status': 'error',
            'message': 'نمی‌توان آخرین ادمین را حذف کرد'
        }), 400
        
    # حذف محصولات کاربر
    Product.query.filter_by(user_id=user.id).delete()
    
    # حذف گزارش‌های کاربر
    Report.query.filter_by(reporter_id=user.id).delete()
    
    # حذف پیام‌های کاربر
    Message.query.filter(
        (Message.sender_id == user.id) | (Message.receiver_id == user.id)
    ).delete()
    
    # حذف مکالمات کاربر
    Conversation.query.filter(
        (Conversation.user1_id == user.id) | (Conversation.user2_id == user.id)
    ).delete()
    
    # حذف کاربر
    db.session.delete(user)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': f'کاربر {user.username} با موفقیت حذف شد'
    })

@bp.route('/delete_category/<int:category_id>', methods=['POST'])
@login_required
def delete_category(category_id):
    """حذف دسته‌بندی - فقط برای ادمین"""
    if not current_user.is_admin:
        return jsonify({
            'status': 'error',
            'message': 'فقط ادمین می‌تواند این عملیات را انجام دهد'
        }), 403
        
    category = Category.query.get_or_404(category_id)
    
    # بررسی وجود محصول در این دسته‌بندی
    products_count = Product.query.filter_by(category_id=category.id).count()
    if products_count > 0:
        return jsonify({
            'status': 'error',
            'message': 'این دسته‌بندی دارای محصول است و نمی‌توان آن را حذف کرد'
        }), 400
        
    # بررسی وجود زیر‌دسته
    subcategories_count = Category.query.filter_by(parent_id=category.id).count()
    if subcategories_count > 0:
        return jsonify({
            'status': 'error',
            'message': 'این دسته‌بندی دارای زیردسته است و نمی‌توان آن را حذف کرد'
        }), 400
        
    # حذف دسته‌بندی
    db.session.delete(category)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': f'دسته‌بندی {category.name} با موفقیت حذف شد'
    })

@bp.route('/fake_payment')
def fake_payment():
    """شبیه‌سازی درگاه پرداخت زیبال بدون نیاز به درگاه واقعی"""
    product_id = request.args.get('product_id')
    amount = request.args.get('amount')
    
    if not product_id or not amount:
        return jsonify({
            'status': 'error',
            'message': 'اطلاعات پرداخت ناقص است'
        }), 400
        
    # اطلاعات پرداخت برای ارسال به callback
    payment_data = {
        'product_id': product_id,
        'amount': amount,
        'status': 'success'
    }
    
    return jsonify({
        'status': 'success',
        'message': 'پرداخت با موفقیت انجام شد',
        'payment_data': payment_data,
        'redirect': url_for('main.payment_callback', **payment_data)
    })

@bp.route('/pay_to_publish/<int:product_id>', methods=['POST'])
@login_required
def pay_to_publish(product_id):
    """پرداخت برای انتشار محصول"""
    product = Product.query.get_or_404(product_id)
    
    # فقط صاحب محصول می‌تواند برای انتشار پرداخت کند
    if current_user.id != product.user_id:
        return jsonify({
            'status': 'error',
            'message': 'شما اجازه انجام این عملیات را ندارید'
        }), 403
        
    # مبلغ پرداخت (به تومان)
    amount = 5000
    
    # ذخیره اطلاعات پرداخت در session
    session['publish_product_id'] = product.id
    session['publish_amount'] = amount
    
    # TODO: اتصال به درگاه پرداخت واقعی
    # اینجا برای تست، مستقیما به صفحه پرداخت موفق هدایت می‌کنیم
    
    return jsonify({
        'status': 'success',
        'message': 'در حال انتقال به درگاه پرداخت',
        'payment_url': url_for('main.fake_payment', product_id=product.id, amount=amount, publish=True),
        'amount': amount
    })

@bp.route('/conversations')
@login_required
def conversations():
    """لیست مکالمات کاربر"""
    # یافتن مکالمات کاربر
    user_conversations = Conversation.query.filter(
        (Conversation.user1_id == current_user.id) | (Conversation.user2_id == current_user.id)
    ).all()
    
    return jsonify({
        'status': 'success',
        'conversations': [format_conversation(convo) for convo in user_conversations]
    })

@bp.route('/conversation/<int:conversation_id>')
@login_required
def conversation(conversation_id):
    """نمایش پیام‌های یک مکالمه"""
    conversation = Conversation.query.get_or_404(conversation_id)
    
    # بررسی دسترسی کاربر به مکالمه
    if current_user.id != conversation.user1_id and current_user.id != conversation.user2_id:
        return jsonify({
            'status': 'error',
            'message': 'شما اجازه دسترسی به این مکالمه را ندارید'
        }), 403
        
    # دریافت پیام‌های مکالمه
    messages = Message.query.filter_by(conversation_id=conversation.id).order_by(Message.timestamp).all()
    
    # دریافت اطلاعات طرف مقابل
    other_user_id = conversation.user2_id if conversation.user1_id == current_user.id else conversation.user1_id
    other_user = User.query.get(other_user_id)
    
    return jsonify({
        'status': 'success',
        'conversation': format_conversation(conversation),
        'messages': [format_message(message) for message in messages],
        'other_user': format_user(other_user) if other_user else None
    })

@bp.route('/start_conversation/<int:user_id>', methods=['GET', 'POST'])
@login_required
def start_conversation(user_id):
    """شروع مکالمه جدید با کاربر دیگر"""
    other_user = User.query.get_or_404(user_id)
    
    # بررسی عدم شروع مکالمه با خود
    if current_user.id == other_user.id:
        return jsonify({
            'status': 'error',
            'message': 'نمی‌توانید با خودتان مکالمه کنید'
        }), 400
        
    # بررسی وجود مکالمه قبلی
    existing_conversation = Conversation.query.filter(
        ((Conversation.user1_id == current_user.id) & (Conversation.user2_id == other_user.id)) |
        ((Conversation.user1_id == other_user.id) & (Conversation.user2_id == current_user.id))
    ).first()
    
    if existing_conversation:
        # اگر مکالمه قبلی وجود داشته باشد، به آن بازمی‌گردیم
        return jsonify({
            'status': 'success',
            'message': 'مکالمه قبلی یافت شد',
            'conversation': format_conversation(existing_conversation),
            'redirect': url_for('main.conversation', conversation_id=existing_conversation.id)
        })
    
    if request.method == 'POST':
        # برای درخواست‌های JSON
        if request.is_json:
            data = request.get_json()
            content = data.get('content', '').strip()
        else:
            # برای درخواست‌های form-data
            content = request.form.get('content', '').strip()
            
        if not content:
            return jsonify({
                'status': 'error',
                'message': 'متن پیام الزامی است'
            }), 400
            
        # ایجاد مکالمه جدید
        conversation = Conversation(
            user1_id=current_user.id,
            user2_id=other_user.id
        )
        db.session.add(conversation)
        db.session.flush()  # ذخیره موقت برای دریافت ID مکالمه
        
        # ایجاد پیام جدید
        message = Message(
            sender_id=current_user.id,
            receiver_id=other_user.id,
            content=content,
            conversation_id=conversation.id
        )
        db.session.add(message)
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'مکالمه با موفقیت آغاز شد',
            'conversation': format_conversation(conversation),
            'redirect': url_for('main.conversation', conversation_id=conversation.id)
        })
        
    # اگر درخواست GET باشد
    return jsonify({
        'status': 'ready',
        'message': 'لطفا پیام خود را وارد کنید',
        'other_user': format_user(other_user)
    })

@bp.route('/send_message', methods=['POST'])
@login_required
def send_message():
    """ارسال پیام جدید در مکالمه"""
    # برای درخواست‌های JSON
    if request.is_json:
        data = request.get_json()
        content = data.get('content', '').strip()
        conversation_id = data.get('conversation_id')
        receiver_id = data.get('receiver_id')
        replied_to_id = data.get('replied_to_id')
    else:
        # برای درخواست‌های form-data
        content = request.form.get('content', '').strip()
        conversation_id = request.form.get('conversation_id')
        receiver_id = request.form.get('receiver_id')
        replied_to_id = request.form.get('replied_to_id')
        
    if not content:
        return jsonify({
            'status': 'error',
            'message': 'متن پیام الزامی است'
        }), 400
        
    if not conversation_id:
        return jsonify({
            'status': 'error',
            'message': 'شناسه مکالمه الزامی است'
        }), 400
        
    if not receiver_id:
        return jsonify({
            'status': 'error',
            'message': 'شناسه گیرنده الزامی است'
        }), 400
        
    # بررسی دسترسی کاربر به مکالمه
    conversation = Conversation.query.get_or_404(conversation_id)
    if current_user.id != conversation.user1_id and current_user.id != conversation.user2_id:
        return jsonify({
            'status': 'error',
            'message': 'شما اجازه دسترسی به این مکالمه را ندارید'
        }), 403
        
    # بررسی وجود پیام پاسخ‌داده‌شده
    if replied_to_id:
        replied_to = Message.query.get(replied_to_id)
        if not replied_to or replied_to.conversation_id != int(conversation_id):
            return jsonify({
                'status': 'error',
                'message': 'پیام پاسخ‌داده‌شده یافت نشد یا به این مکالمه تعلق ندارد'
            }), 400
    
    # آپلود فایل اگر وجود داشته باشد
    file_path = None
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename:
            file_path = save_image(file, 'static/uploads/messages')
            
    # ایجاد پیام جدید
    message = Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        content=content,
        conversation_id=conversation_id,
        replied_to_id=replied_to_id,
        file_path=file_path
    )
    
    db.session.add(message)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'پیام با موفقیت ارسال شد',
        'data': format_message(message)
    })

@bp.route('/delete_message/<int:message_id>', methods=['POST'])
@login_required
def delete_message(message_id):
    """حذف پیام"""
    message = Message.query.get_or_404(message_id)
    
    # فقط فرستنده پیام می‌تواند آن را حذف کند
    if current_user.id != message.sender_id:
        return jsonify({
            'status': 'error',
            'message': 'شما اجازه حذف این پیام را ندارید'
        }), 403
        
    # حذف پیام
    db.session.delete(message)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'پیام با موفقیت حذف شد'
    })

@bp.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    """چت‌بات هوش مصنوعی"""
    if request.method == 'POST':
        # برای درخواست‌های JSON
        if request.is_json:
            data = request.get_json()
            user_query = data.get('query', '').strip()
        else:
            # برای درخواست‌های form-data
            user_query = request.form.get('query', '').strip()
            
        if not user_query:
            return jsonify({
                'status': 'error',
                'message': 'متن پرسش الزامی است'
            }), 400
            
        # TODO: اتصال به سرویس هوش مصنوعی
        # اینجا برای تست، پاسخ ثابت برمی‌گردانیم
        bot_response = f"پاسخ به پرسش: {user_query}"
        
        # پاسخ هوش مصنوعی
        response_data = {
            'status': 'success',
            'query': user_query,
            'response': bot_response,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # ذخیره تعامل با چت‌بات در صورت لاگین بودن کاربر
        if current_user.is_authenticated:
            interaction = ChatBotInteraction(
                user_id=current_user.id,
                user_query=user_query,
                bot_response=bot_response
            )
            db.session.add(interaction)
            db.session.commit()
            
            # پیشنهاد محصولات مرتبط
            related_products = Product.query.filter(
                Product.status == 'published',
                db.or_(
                    Product.name.ilike(f'%{user_query}%'),
                    Product.description.ilike(f'%{user_query}%')
                )
            ).limit(3).all()
            
            if related_products:
                response_data['related_products'] = [format_product(product) for product in related_products]
        
        return jsonify(response_data)
        
    # اگر درخواست GET باشد
    return jsonify({
        'status': 'ready',
        'message': 'لطفا پرسش خود را وارد کنید'
    })

@bp.route('/uploads/<filename>')
def uploaded_file(filename):
    """مسیر دسترسی به فایل‌های آپلود شده"""
    return send_from_directory('static/uploads', filename)

@bp.route('/search')
def search():
    """جستجوی محصولات"""
    query = request.args.get('q', '').strip()
    category_id = request.args.get('category_id')
    
    if not query and not category_id:
        return jsonify({
            'status': 'error',
            'message': 'پارامترهای جستجو ناقص است'
        }), 400
        
    search_query = Product.query.filter(Product.status == 'published')
    
    # جستجو بر اساس متن
    if query:
        search_query = search_query.filter(
            db.or_(
                Product.name.ilike(f'%{query}%'),
                Product.description.ilike(f'%{query}%')
            )
        )
        
    # فیلتر بر اساس دسته‌بندی
    if category_id:
        search_query = search_query.filter(Product.category_id == category_id)
        
    # دریافت نتایج
    products = search_query.order_by(
        db.case(
            (Product.is_promoted == True, 1),
            else_=0
        ).desc(),
        Product.created_at.desc()
    ).all()
    
    return jsonify({
        'status': 'success',
        'query': query,
        'category_id': category_id,
        'count': len(products),
        'products': [format_product(product) for product in products]
    })

@bp.route('/api/products')
def api_products():
    """API برای دریافت لیست محصولات"""
    products = Product.query.filter(Product.status == 'published').order_by(Product.created_at.desc()).all()
    
    return jsonify({
        'status': 'success',
        'count': len(products),
        'products': [format_product(product) for product in products]
    })

@bp.route('/api/product/<int:product_id>')
def api_product_detail(product_id):
    """API برای دریافت جزئیات محصول"""
    product = Product.query.get_or_404(product_id)
    
    # افزایش تعداد بازدید
    if not current_user.is_authenticated or current_user.id != product.user_id:
        product.views += 1
        db.session.commit()
    
    return jsonify({
        'status': 'success',
        'product': format_product(product),
        'seller': format_user(product.owner) if product.owner else None
    })