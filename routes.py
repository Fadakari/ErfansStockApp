import os
import logging
from flask import render_template, redirect, url_for, flash, request, Blueprint, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse
from aplication import db
from models import User, Product, Category
from utils import save_image
from datetime import datetime, timedelta
import requests
from models import ProductType  # جایگزین yourapp با نام پروژه شما


main = Blueprint('main', __name__)

logging.basicConfig(level=logging.DEBUG)

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    search = request.args.get('search', '').strip()
    category_id = request.args.get('category', '')

    query = Product.query

    if search:
        # جستجو در نام و توضیحات محصول
        search_filter = db.or_(
            Product.name.ilike(f'%{search}%'),
            Product.description.ilike(f'%{search}%')
        )
        query = query.filter(search_filter)

    if category_id:
        query = query.filter_by(category_id=category_id)
        
    promoted_products = query.filter(Product.promoted_until > datetime.utcnow()).order_by(Product.promoted_until.desc())
    normal_products = query.filter(db.or_(Product.promoted_until == None, Product.promoted_until <= datetime.utcnow())).order_by(Product.created_at.desc())
    # مرتب‌سازی بر اساس جدیدترین محصولات
    query = query.order_by(Product.updated_at.desc().nullslast(), Product.created_at.desc())

    products = promoted_products.union(normal_products).all()
    categories = Category.query.all()
    return render_template('products.html', products=products, categories=categories, datetime=datetime)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user is None or not user.check_password(request.form['password']):
            flash('نام کاربری یا رمز عبور نامعتبر است')
            return redirect(url_for('main.login'))

        login_user(user)
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            next_page = url_for('main.index')
        return redirect(next_page)

    return render_template('login.html')

@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@bp.route('/dashboard')
@login_required
def dashboard():
    products = Product.query.filter_by(user_id=current_user.id).all()
    categories = Category.query.all()
    return render_template('dashboard.html', products=products, categories=categories)

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


@bp.route('/product/new', methods=['GET', 'POST'])
@login_required
def new_product():
    if request.method == 'POST':
        try:
            # دریافت مقادیر از فرم
            name = request.form.get('name')
            description = request.form.get('description')
            price = request.form.get('price')
            category_id = request.form.get('category_id')
            promote = request.form.get('promote') == 'on'
            address = request.form.get("address")
            postal_code = request.form.get("postal_code")
            product_type = request.form.get("product_type")

            if product_type in ProductType.__members__:
                product_type = ProductType[product_type]  # مقدار متنی رو به Enum تبدیل کن
            else:
                product_type = None
            # چاپ مقادیر در سرور
            print(f"Address: {address}")
            print(f"Postal Code: {postal_code}")
            print(f"Product Type: {product_type}")

            if not name or not price:
                flash('لطفاً نام و قیمت محصول را وارد کنید')
                categories = Category.query.all()
                return render_template('product_form.html', categories=categories)

            try:
                price = float(price)
            except ValueError:
                flash('لطفاً قیمت معتبر وارد کنید')
                categories = Category.query.all()
                return render_template('product_form.html', categories=categories)
            

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
                product_type=product_type
            )

            print(f"Received Product Type: {product_type}")
            print(f"Available Enum Keys: {list(ProductType.__members__.keys())}")


            if promote:
                product.promoted_until = datetime.utcnow() + timedelta(days=30)

            db.session.add(product)
            db.session.commit()
            saved_product = Product.query.order_by(Product.id.desc()).first()
            print(f"Saved Product: {saved_product.address}, {saved_product.postal_code}, {saved_product.product_type}")


            flash('محصول با موفقیت ایجاد شد')
            return redirect(url_for('main.dashboard'))

        except Exception as e:
            db.session.rollback()
            logging.error(f"Error in new_product: {str(e)}")
            flash('خطا در ایجاد محصول')
            return render_template('product_form.html')

        
        
    categories = Category.query.all()
    return render_template('product_form.html', categories=categories)



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
            promote = request.form.get('promote') == 'on'
            product.address = request.form.get("address")
            product.postal_code = request.form.get("postal_code")

            # دریافت و تبدیل product_type
            product_type = request.form.get("product_type")
            print(f"Received Product Type: {product_type}")  # بررسی مقدار دریافتی

            if product_type in ProductType.__members__:
                product.product_type = ProductType[product_type]
            else:
                product.product_type = None

            print(f"Final Product Type Before Save: {product.product_type}")  # بررسی مقدار قبل از ذخیره

            # تبدیل مقدار قیمت به float
            try:
                product.price = float(request.form.get('price'))
            except ValueError:
                flash('لطفاً قیمت معتبر وارد کنید')
                return render_template('product_form.html', product=product)

            # بررسی آپلود تصویر جدید
            image = request.files.get('image')
            if image and image.filename:
                new_image_path = save_image(image)
                if new_image_path:
                    if product.image_path:
                        old_image_path = os.path.join('static/uploads', product.image_path)
                        if os.path.exists(old_image_path):
                            os.remove(old_image_path)
                    product.image_path = new_image_path

            # بررسی وضعیت تبلیغ
            if promote and not product.promoted_until:
                product.promoted_until = datetime.utcnow() + timedelta(days=30)
            elif not promote:
                product.promoted_until = None

            db.session.commit()

            # بررسی مقدار ذخیره‌شده در دیتابیس
            saved_product = Product.query.get(product.id)
            print(f"Saved Product Type in DB: {saved_product.product_type}")

            flash('محصول با موفقیت به‌روزرسانی شد')
            return redirect(url_for('main.dashboard'))

        except Exception as e:
            db.session.rollback()
            logging.error(f"Error updating product: {str(e)}")
            flash('خطا در به‌روزرسانی محصول')

    categories = Category.query.all()
    return render_template('product_form.html', product=product, categories=categories)


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

@bp.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    categories = Category.query.all()
    user = User.query.get(product.user_id)  # یا می‌توانید با استفاده از ارتباطات sqlalchemy این اطلاعات را بدست آورید
    phone = user.phone if user else None
    return render_template('product_detail.html', user=user, product=product, categories=categories, phone=phone)

@bp.route('/init-categories')
def init_categories():
    categories = [
        'ابزار برقی استوک',
        'ابزار باغبانی استوک', 
        'ابزار جوشکاری استوک',
        'ابزار مکانیکی استوک',
        'ابزار نجاری استوک',
        'ابزار بنایی استوک',
        'ابزار تراشکاری استوک',
        'ابزار لوله‌کشی استوک',
        'ابزار رنگ‌کاری استوک',
        'تجهیزات ایمنی استوک',
        'تجهیزات کارگاهی استوک',
        'ابزار های شارژی',
        'ابزار های کرگیر',
        'سایر ابزارآلات استوک'
    ]
    
    for cat_name in categories:
        if not Category.query.filter_by(name=cat_name).first():
            category = Category(name=cat_name)
            db.session.add(category)
    
    try:
        db.session.commit()
        flash('دسته‌بندی‌ها با موفقیت ایجاد شدند')
    except Exception as e:
        db.session.rollback()
        flash('خطا در ایجاد دسته‌بندی‌ها')
    
    return redirect(url_for('main.index'))



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

            # بررسی اگر هیچ ادمینی در سیستم وجود ندارد، اولین کاربر ادمین شود
            is_first_admin = User.query.filter_by(is_admin=True).count() == 0

            user = User(username=username, email=email, phone=phone, national_id=national_id)
            user.set_password(password)
            
            if is_first_admin:
                user.is_admin = True  # تبدیل اولین کاربر به ادمین

            db.session.add(user)
            db.session.commit()

            flash('ثبت‌نام با موفقیت انجام شد. اکنون می‌توانید وارد شوید')
            return redirect(url_for('main.login'))

        except Exception as e:
            db.session.rollback()
            logging.error(f"Error in signup: {str(e)}")
            flash('خطا در ثبت‌نام. لطفاً دوباره تلاش کنید')
            return render_template('signup.html')

    return render_template('signup.html')  # این خط برای نمایش فرم ثبت‌نام

        

@bp.route("/payment/start/<int:product_id>", methods=["GET"])
def start_payment(product_id):
    product = Product.query.get(product_id)
    if not product:
        return jsonify({"error": "Product not found"}), 404

    amount = 70000  # مبلغ پرداختی
    merchant = "65717f98c5d2cb000c3603da"
    callback_url = "http://localhost:5000/fake-callback"

    data = {
        "merchant": merchant,
        "amount": amount,
        "callbackUrl": callback_url,
    }

    response = requests.post("https://gateway.zibal.ir/v1/request", json=data)
    result = response.json()

    print("Status Code:", response.status_code)
    print("Response:", result)

    if result["result"] == 100:
        return redirect(f"https://gateway.zibal.ir/start/{result['trackId']}")
    else:
        return jsonify({"error": "خطا در ایجاد پرداخت"}), 400
    
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
    result = {"result": 100}  # فرض می‌کنیم پرداخت موفق بوده

    if result["result"] == 100:
        product.promoted_until = datetime.utcnow() + timedelta(days=7)  # 🔹 نردبان برای ۷ روز
        db.session.commit() # ذخیره تغییرات در دیتابیس
        db.session.refresh(product)  # اطمینان از دریافت مقدار جدید از دیتابیس


        # چاپ اطلاعات محصول بعد از بروزرسانی
        print(f"Product after update: {product}, updated_at: {product.updated_at}")

        return jsonify({"message": "پرداخت موفق بود، محصول نردبان شد!"})
    else:
        return jsonify({"error": "پرداخت ناموفق بود"}), 400
    
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



@bp.route("/admin", methods=["GET", "POST"])
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash("شما دسترسی به این بخش را ندارید")
        return redirect(url_for('main.index'))
    
    users = User.query.all()  # نمایش تمام کاربران
    categories = Category.query.all()  # نمایش تمام دسته‌بندی‌ها
    return render_template("admin_dashboard.html", users=users, categories=categories)



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



    
@bp.route("/fake-payment", methods=["POST"])
def fake_payment():
    """شبیه‌سازی درگاه پرداخت زیبال بدون نیاز به درگاه واقعی"""
    track_id = "123456789"  # مقدار فیک برای تست
    return jsonify({"result": 100, "trackId": track_id})


    return render_template('signup.html')