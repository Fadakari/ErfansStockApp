import os
import logging
from flask import render_template, redirect, url_for, flash, request, Blueprint
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse
from app import db
from models import User, Product, Category
from utils import save_image

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
        
    # مرتب‌سازی بر اساس جدیدترین محصولات
    query = query.order_by(Product.created_at.desc())

    products = query.all()
    categories = Category.query.all()
    return render_template('products.html', products=products, categories=categories)

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

@bp.route('/product/new', methods=['GET', 'POST'])
@login_required
def new_product():
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            description = request.form.get('description')
            price = request.form.get('price')
            category_id = request.form.get('category_id')

            if not name or not price:
                flash('لطفاً نام و قیمت محصول را وارد کنید')
                categories = Category.query.all()
                return render_template('product_form.html', categories=categories)

            try:
                price = float(price)
            except ValueError:
                flash('لطفاً قیمت معتبر وارد کنید')
                return render_template('product_form.html')

            image_path = None
            if 'image' in request.files:
                image = request.files['image']
                if image and image.filename:
                    image_path = save_image(image)

            product = Product(
                name=name,
                description=description,
                price=price,
                image_path=image_path,
                user_id=current_user.id,
                category_id=category_id
            )

            db.session.add(product)
            db.session.commit()

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
    if product.user_id != current_user.id:
        flash('شما اجازه ویرایش این محصول را ندارید')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        try:
            product.name = request.form.get('name')
            product.description = request.form.get('description')
            product.category_id = request.form.get('category_id')
            try:
                product.price = float(request.form.get('price'))
            except ValueError:
                flash('لطفاً قیمت معتبر وارد کنید')
                return render_template('product_form.html', product=product)

            image = request.files.get('image')
            if image and image.filename:
                new_image_path = save_image(image)
                if new_image_path:
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
            logging.error(f"Error updating product: {str(e)}")
            flash('خطا در به‌روزرسانی محصول')

    categories = Category.query.all()
    return render_template('product_form.html', product=product, categories=categories)

@bp.route('/product/<int:id>/delete', methods=['POST'])
@login_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    if product.user_id != current_user.id:
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
    return render_template('product_detail.html', product=product, categories=categories)

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
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        try:
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')

            if not username or not email or not password:
                flash('لطفاً تمام فیلدها را پر کنید')
                return render_template('signup.html')

            if User.query.filter_by(username=username).first():
                flash('این نام کاربری قبلاً استفاده شده است')
                return render_template('signup.html')

            if User.query.filter_by(email=email).first():
                flash('این ایمیل قبلاً استفاده شده است')
                return render_template('signup.html')

            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            flash('ثبت‌نام با موفقیت انجام شد. اکنون می‌توانید وارد شوید')
            return redirect(url_for('main.login'))

        except Exception as e:
            db.session.rollback()
            logging.error(f"Error in signup: {str(e)}")
            flash('خطا در ثبت‌نام. لطفاً دوباره تلاش کنید')
            return render_template('signup.html')

    return render_template('signup.html')