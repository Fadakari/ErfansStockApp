import os
import logging
from flask import render_template, redirect, url_for, flash, request, Blueprint, jsonify, session, url_for
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse
from aplication import db
from models import User, Product, Category, EditProfileForm, Message, Conversation
from utils import save_image
from datetime import datetime, timedelta
import random
import requests
from models import ProductType  # جایگزین yourapp با نام پروژه شما
from aplication import limiter


main = Blueprint('main', __name__)

logging.basicConfig(level=logging.DEBUG)

bp = Blueprint('main', __name__)



# لیست استان‌ها و شهرهای مربوطه
@limiter.limit("5 per minute")
@bp.route('/')
def index():
    search = request.args.get('search', '').strip()
    province_search = request.args.get('province_search', '').strip()
    city_search = request.args.get('city_search', '').strip()
    category_id = request.args.get('category', '').strip()  # جستجو بر اساس دسته‌بندی
    address_search = request.args.get('address_search', '').strip()

    query = Product.query

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






@limiter.limit("5 per minute")
@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user is None or not user.check_password(request.form['password']):
            flash('نام کاربری یا رمز عبور نامعتبر است')
            return redirect(url_for('main.login'))

        # ارسال OTP به شماره کاربر
        otp = random.randint(1000, 9999)
        session['otp_code'] = otp
        session['user_id'] = user.id  # ذخیره شناسه کاربر برای ورود

        # ارسال OTP به شماره تلفن (در محیط واقعی اینجا پیامک می‌فرستیم)
        print(f"کد OTP برای ورود به حساب: {otp}")  # در محیط واقعی باید ارسال پیامک بشه

        return redirect(url_for('main.verify_login'))  # هدایت به صفحه تایید OTP

    return render_template('login.html')

@limiter.limit("5 per minute")
@bp.route('/verify_login', methods=['GET', 'POST'])
def verify_login():
    if request.method == 'POST':
        entered_code = request.form.get('code')

        if entered_code == str(session.get('otp_code')):  # بررسی کد وارد شده
            user = User.query.get(session['user_id'])

            # ورود کاربر پس از تایید کد OTP
            login_user(user)

            # پاک کردن سشن‌ها
            session.pop('otp_code', None)
            session.pop('user_id', None)

            flash('ورود با موفقیت انجام شد!', 'success')
            return redirect(url_for('main.index'))
        else:
            flash('کد وارد شده اشتباه است!', 'danger')

    return render_template('verify_login.html')



@limiter.limit("5 per minute")
@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@bp.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    # دریافت محصولات کاربر
    products = Product.query.filter_by(user_id=current_user.id).all()
    
    # دریافت دسته‌بندی‌ها
    categories = Category.query.all()
    
    # فرم ویرایش پروفایل
    form = EditProfileForm(obj=current_user)
    
    # دریافت محصولات پر بازدید (محصولاتی که بیشترین تعداد بازدید دارند)
    top_products = Product.query.order_by(Product.views.desc()).limit(3).all()

    # اگر تعداد محصولات کمتر از ۴ باشد، فقط پر بازدیدترین محصول را نمایش دهیم
    if len(top_products) < 4:
        top_products = top_products[:1]  # نمایش فقط یک محصول پر بازدید

    # بررسی و ارسال فرم ویرایش پروفایل
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        flash('اطلاعات شما با موفقیت بروزرسانی شد!')
        return redirect(url_for('main.dashboard'))
    
    # رندر کردن صفحه داشبورد همراه با محصولات پر بازدید
    return render_template('dashboard.html', 
                           products=products, 
                           categories=categories, 
                           form=form, 
                           top_products=top_products)


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
            name = request.form.get('name')
            description = request.form.get('description')
            price = request.form.get('price')
            category_id = request.form.get('category_id')
            product_type = request.form.get('product_type')

            province = request.form.get("province")
            city = request.form.get("city")
            address = f"{province}-{city}"  # ذخیره استان و شهر به این فرمت: "تهران-شهریار"

            postal_code = request.form.get("postal_code")

            image_path = None
            if 'image' in request.files:
                image = request.files['image']
                if image and image.filename:
                    image_path = save_image(image)

            product = Product(
                name=name,
                description=description,
                price=price,
                image_path=image.filename if image else None,
                user_id=current_user.id,
                category_id=category_id,
                address=address,
                postal_code=postal_code,
                product_type=ProductType[product_type] if product_type in ProductType.__members__ else None
            )

            db.session.add(product)
            db.session.commit()
            flash('محصول با موفقیت ایجاد شد')
            return redirect(url_for('main.dashboard'))

        except Exception as e:
            db.session.rollback()
            flash('خطا در ایجاد محصول')
            return render_template('product_form.html')

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
            product.address = f"{province}-{city}"  # ذخیره استان و شهر در قالب "استان-شهر"

            product.postal_code = request.form.get("postal_code")

            # دریافت و تبدیل product_type
            product_type = request.form.get("product_type")
            if product_type in ProductType.__members__:
                product.product_type = ProductType[product_type]
            else:
                product.product_type = None

            # بررسی آپلود تصویر جدید
            image = request.files.get('image')
            if image and image.filename:
                new_image_path = save_image(image)
                if new_image_path:
                    # حذف تصویر قدیمی
                    if product.image_path:
                        old_image_path = os.path.join('static/uploads', product.image_path)
                        if os.path.exists(old_image_path):
                            os.remove(old_image_path)
                    product.image_path = new_image_path

            db.session.commit()
            flash('محصول با موفقیت به‌روزرسانی شد')
            return redirect(url_for('main.dashboard'))

        except Exception as e:
            db.session.rollback()
            flash('خطا در به‌روزرسانی محصول')

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
        return redirect(url_for('main.index'))  # بازگشت به صفحه اصلی اگر لاگین است

    if request.method == 'POST':
        try:
            username = request.form.get('username')
            email = request.form.get('email')
            phone = request.form.get('phone')
            national_id = request.form.get('national_id')
            password = request.form.get('password')

            print(f"Username: {username}, Email: {email}, Phone: {phone}, National ID: {national_id}")

            if not username or not email or not phone or not national_id or not password:
                flash('لطفاً تمام فیلدها را پر کنید')
                return render_template('signup.html')

            if User.query.filter_by(username=username).first():
                flash('این نام کاربری قبلاً استفاده شده است')
                return render_template('signup.html')

            if User.query.filter_by(email=email).first():
                flash('این ایمیل قبلاً استفاده شده است')
                return render_template('signup.html')
            
            if User.query.filter_by(phone=phone).first():
                flash('این شماره تماس قبلاً استفاده شده است')
                return render_template('signup.html')

            if User.query.filter_by(national_id=national_id).first():
                flash('این کد ملی قبلاً ثبت شده است')
                return render_template('signup.html')

            # تولید کد تأیید و ذخیره آن در سشن
            verification_code = random.randint(1000, 9999)
            session['verification_code'] = verification_code
            session['signup_data'] = {
                'username': username,
                'email': email,
                'phone': phone,
                'national_id': national_id,
                'password': password
            }

            print(f"کد تأیید برای {phone}: {verification_code}")  # در محیط واقعی باید پیامک شود

            return redirect(url_for('main.verify'))  # هدایت به صفحه تأیید شماره

        except Exception as e:
            db.session.rollback()
            logging.error(f"Error in signup: {str(e)}")
            flash('خطا در ثبت‌نام. لطفاً دوباره تلاش کنید')
            return render_template('signup.html')

    return render_template('signup.html')  # نمایش فرم ثبت‌نام


@limiter.limit("5 per minute")
@bp.route('/verify', methods=['GET', 'POST'])
def verify():
    if request.method == 'POST':
        entered_code = request.form.get('code')
        
        if entered_code == str(session.get('verification_code')):  # بررسی کد وارد شده
            data = session.get('signup_data')
            if not data:
                flash('خطای سیستمی! لطفاً دوباره ثبت‌نام کنید.', 'danger')
                return redirect(url_for('main.signup'))
            
            # ذخیره کاربر در دیتابیس پس از تأیید شماره
            user = User(
                username=data['username'],
                email=data['email'],
                phone=data['phone'],
                national_id=data['national_id']
            )
            user.set_password(data['password'])

            db.session.add(user)
            db.session.commit()

            # پاک کردن سشن بعد از ثبت موفق
            session.pop('verification_code', None)
            session.pop('signup_data', None)

            flash('ثبت‌نام با موفقیت انجام شد!', 'success')
            return redirect(url_for('main.login'))

        else:
            flash('کد وارد شده اشتباه است!', 'danger')

    return render_template('verify.html')


        

@limiter.limit("5 per minute")
@bp.route("/payment/start/<int:product_id>", methods=["GET"])
def start_payment(product_id):
    product = Product.query.get(product_id)
    if not product:
        return jsonify({"error": "Product not found"}), 404

    amount = 70000
    merchant = "65717f98c5d2cb000c3603da"
    callback_url = f"http://localhost:5000/payment/callback?product_id={product_id}"

    data = {
        "merchant": merchant,
        "amount": amount,
        "callbackUrl": callback_url,
    }

    response = requests.post("https://gateway.zibal.ir/v1/request", json=data)
    result = response.json()

    print("Status Code:", response.status_code)
    print("Response:", result)

    if result.get("result") == 100 and "trackId" in result:
        return redirect(f"https://gateway.zibal.ir/start/{result['trackId']}")
    else:
        return jsonify({"error": "خطا در ایجاد پرداخت"}), 400

@limiter.limit("5 per minute")
@bp.route("/payment/callback", methods=["GET", "POST"])
def payment_callback():
    """بررسی پرداخت و نردبان کردن محصول"""
    if request.method == "POST":
        data = request.form
    else:
        data = request.args

    track_id = data.get("trackId")
    product_id = data.get("product_id")  # گرفتن شناسه محصول

    if not track_id or not product_id:
        return jsonify({"error": "No track ID or product ID"}), 400

    # تبدیل product_id به عدد صحیح
    try:
        product_id = int(product_id)
    except ValueError:
        return jsonify({"error": "Invalid product ID"}), 400

    # دریافت محصول از دیتابیس
    product = Product.query.get(product_id)
    if not product:
        return jsonify({"error": "Product not found"}), 404

    # چاپ اطلاعات محصول قبل از بروزرسانی
    print(f"Product before update: {product}, updated_at: {product.updated_at}")

    # شبیه‌سازی پاسخ موفق از زیبال
    # ارسال درخواست به زیبال برای بررسی وضعیت پرداخت
    verify_response = requests.post("https://gateway.zibal.ir/v1/verify", json={
        "merchant": "65717f98c5d2cb000c3603da",
        "trackId": track_id
    })
    verify_result = verify_response.json()

    # چاپ برای دیباگ
    print("Verify response:", verify_result)

    if verify_result.get("result") == 100:
        product.promoted_until = datetime.utcnow() + timedelta(days=7)
        db.session.commit()
        db.session.refresh(product)
        return jsonify({"message": "پرداخت موفق بود، محصول نردبان شد!"})
    else:
        return jsonify({"error": "پرداخت ناموفق بود"}), 400


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
    product.promoted_until = datetime.utcnow() + timedelta(seconds=10)
    db.session.commit()

    flash('محصول به مدت 10 ثانیه نردبان شد!')
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

    return render_template("admin_dashboard.html", users=users, categories=categories)




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

@bp.route('/conversations')
@login_required
def conversations():
    convs = Conversation.query.filter(
        (Conversation.user1_id == current_user.id) | 
        (Conversation.user2_id == current_user.id)
    ).all()
    return render_template('conversations.html', conversations=convs)


@bp.route('/chat/<int:user_id>', methods=['GET', 'POST'])
@login_required
def chat(user_id):
    user = User.query.get_or_404(user_id)
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user.id)) |
        ((Message.sender_id == user.id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.timestamp).all()
    
    # چک می‌کنیم آیا مکالمه‌ای هست
    convo = Conversation.query.filter(
        ((Conversation.user1_id == current_user.id) & (Conversation.user2_id == user_id)) |
        ((Conversation.user1_id == user_id) & (Conversation.user2_id == current_user.id))
    ).first()

    if not convo:
        convo = Conversation(user1_id=current_user.id, user2_id=user_id)
        db.session.add(convo)
        db.session.commit()

    # دریافت پیام‌ها
    messages = convo.messages.order_by(Message.timestamp.asc()).all()

    if request.method == 'POST':
        content = request.form.get('content')
        if content:
            # اضافه کردن receiver_id در زمان ساخت پیام
            msg = Message(sender_id=current_user.id, receiver_id=user.id, conversation_id=convo.id, content=content)
            db.session.add(msg)
            db.session.commit()
            return redirect(url_for('main.chat', user_id=user_id))

    return render_template('chat.html', messages=messages, user_id=user_id, user=user)



@bp.route('/edit_message/<int:message_id>', methods=['POST'])
@login_required
def edit_message(message_id):
    msg = Message.query.get_or_404(message_id)
    if msg.sender_id != current_user.id:
        return jsonify(success=False), 403
    data = request.get_json()
    msg.content = data.get('content', '').strip()
    db.session.commit()
    return jsonify(success=True)

@bp.route('/delete_message/<int:message_id>', methods=['POST'])
@login_required
def delete_message(message_id):
    msg = Message.query.get_or_404(message_id)
    if msg.sender_id != current_user.id:
        return jsonify(success=False), 403
    db.session.delete(msg)
    db.session.commit()
    return jsonify(success=True)