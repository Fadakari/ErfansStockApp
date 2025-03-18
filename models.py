from datetime import datetime, timedelta  # فقط یک بار وارد شد
from aplication import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from enum import Enum
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(11), unique=True, nullable=False)
    national_id = db.Column(db.String(10), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    # back_populates برای هماهنگ کردن با مدل Product
    products = db.relationship('Product', backref='owner', lazy=True)
    is_admin = db.Column(db.Boolean, default=False)
    # اضافه کردن overlaps
    items = db.relationship('Product', back_populates='seller', lazy=True, overlaps="owner,products")  # استفاده از overlaps

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    products = db.relationship('Product', backref='category', lazy=True)

def default_expiry():
    return datetime.utcnow() + timedelta(seconds=60)

class ProductType(Enum):
    NEW = 'نو'
    STOCK = 'استوک'
    USED = 'دست دوم'
    NEEDS_REPAIR = 'نیاز به تعمیر جزئی'

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    image_path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    promoted_until = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    seller = db.relationship('User', back_populates='items', lazy=True)
    is_promoted = db.Column(db.Boolean, default=False)
    address = db.Column(db.String(200), nullable=True)  # آدرس
    postal_code = db.Column(db.String(20), nullable=True)  # کد پستی
    product_type = db.Column(db.Enum(ProductType), nullable=True)


    def __init__(self, name, description, price, image_path, user_id, category_id, promoted_until=None, address=None, postal_code=None, product_type=None):
        self.name = name
        self.description = description
        self.price = price
        self.image_path = image_path
        self.user_id = user_id
        self.category_id = category_id
        self.promoted_until = promoted_until
        self.address = address
        self.postal_code = postal_code
        self.product_type = product_type

class ProductForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[DataRequired()])
    price = FloatField('Price', validators=[DataRequired()])
    address = StringField('Address', validators=[DataRequired()])
    postal_code = StringField('Postal Code', validators=[DataRequired()])
    product_type = SelectField('Product Type', choices=[(product_type.value, product_type.name) for product_type in ProductType], coerce=str)
    category_id = SelectField('Category', choices=[], coerce=int)  # برای نمایش دسته‌بندی‌ها باید آن‌ها را به صورت داینامیک وارد کنید
    submit = SubmitField('Add Product')

