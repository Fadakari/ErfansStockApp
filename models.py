from datetime import datetime, timedelta  # فقط یک بار وارد شد
from aplication import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from enum import Enum
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, TextAreaField, SelectField, SubmitField
from wtforms.validators import Email, DataRequired, Length

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    phone = db.Column(db.String(11), unique=True, nullable=True)
    national_id = db.Column(db.String(10), unique=True, nullable=True)
    password_hash = db.Column(db.String(256))

    bazaar_account_id = db.Column(db.String(128), unique=True, nullable=True)
    bazaar_access_token = db.Column(db.Text)
    bazaar_refresh_token = db.Column(db.Text, nullable=True)
    # back_populates برای هماهنگ کردن با مدل Product
    products = db.relationship('Product', back_populates='owner', lazy=True)
    is_admin = db.Column(db.Boolean, default=False)
    # اضافه کردن overlaps

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    

class SignupTempData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(11), unique=True, nullable=False)
    code = db.Column(db.String(4), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)

    def is_expired(self):
        return datetime.utcnow() > self.expires_at




class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    icon = db.Column(db.String(50), nullable=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)  # اضافه کردن ارتباط والد و فرزند
    subcategories = db.relationship('Category', backref=db.backref('parent', remote_side=[id]), lazy=True)
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
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    image_path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    promoted_until = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_promoted = db.Column(db.Boolean, default=False)
    address = db.Column(db.String(1000), nullable=False)
    postal_code = db.Column(db.String(20), nullable=True)
    product_type = db.Column(db.Enum(ProductType), nullable=False)
    views = db.Column(db.Integer, default=0)  # تعداد بازدید، مقدار اولیه صفر
    owner = db.relationship('User', back_populates='products', lazy=True)
    status = db.Column(db.String(20), default='pending')
    expires_at = db.Column(db.DateTime, nullable=True)
    brand = db.Column(db.String(100), nullable=True)

    def __init__(self, name, description, price, image_path, user_id, category_id, promoted_until=None, address=None, postal_code=None, product_type=None, views=0, status='pending', expires_at=None, brand=None):
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
        self.views = views  # مقدار تعداد بازدید را به ویژگی اضافه کنید
        self.status = status
        self.expires_at = expires_at if expires_at else datetime.utcnow() + timedelta(days=30)
        self.brand = brand


    # تبدیل مقدار متنی به مقدار Enum
        if product_type:
            print(f"Raw Product Type Before Enum Conversion: {product_type}")  # مقدار قبل از تبدیل
            if isinstance(product_type, str) and product_type in ProductType.__members__:
                self.product_type = ProductType[product_type]
            elif isinstance(product_type, ProductType):  # شاید مقدار از قبل به Enum تبدیل شده باشه
                self.product_type = product_type
            else:
                self.product_type = None
            print(f"Final Product Type in __init__: {self.product_type}")  # مقدار نهایی
        else:
            self.product_type = None




class ProductForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[DataRequired()])
    price = FloatField('Price', validators=[DataRequired()])
    address = StringField('Address', validators=[DataRequired()])
    postal_code = StringField('Postal Code', validators=[DataRequired()])
    product_type = SelectField(
        'Product Type', 
        choices=[(product_type.name, product_type.value) for product_type in ProductType], 
        coerce=str
    )
    category_id = SelectField('Category', choices=[], coerce=int)  # برای نمایش دسته‌بندی‌ها باید آن‌ها را به صورت داینامیک وارد کنید
    brand = SelectField('Brand', choices=[
        ('bosch', 'Bosch'), 
        ('makita', 'Makita'), 
        ('dewalt', 'DeWalt'),
        ('milwaukee', 'Milwaukee'),
        ('hilti', 'Hilti'),
        ('stanley', 'Stanley'),
        ('ingersoll_rand', 'Ingersoll Rand'),
        ('black_decker', 'Black & Decker'),
        ('metabo', 'Metabo'),
        ('hitachi', 'Hitachi'),
        ('ridgid', 'Ridgid'),
        ('ryobi', 'Ryobi'),
        ('festool', 'Festool'),
        ('einhell', 'Einhell'),
        ('ronix', 'Ronix'),
        ('ingco', 'INGCO'),
        ('total', 'TOTAL'),
        ('tactix', 'Tactix'),
        ('kress', 'Kress'),
        ('skil', 'Skil'),
    ], validators=[DataRequired()])
    submit = SubmitField('Add Product')


class EditProfileForm(FlaskForm):
    username = StringField('نام کاربری', validators=[DataRequired()])
    email = StringField('ایمیل', validators=[DataRequired(), Email()])
    phone = StringField('شماره تماس جدید', validators=[Length(min=10, max=15)])
    submit = SubmitField('ذخیره تغییرات')


# models.py
class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user2_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    user1 = db.relationship('User', foreign_keys=[user1_id])
    user2 = db.relationship('User', foreign_keys=[user2_id])

    # تغییر backref به back_populates
    messages = db.relationship('Message', back_populates='conversation', lazy=True)



class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'))
    replied_to_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=True)
    file_path = db.Column(db.String(255), nullable=True)
    sender = db.relationship('User', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])
    
    # تغییر backref به back_populates
    conversation = db.relationship('Conversation', back_populates='messages')
    
    replied_to = db.relationship('Message', remote_side=[id], backref=db.backref('replies', lazy=True), uselist=False)



class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship('Product', backref='reports')
    reporter = db.relationship('User')


class ChatBotInteraction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user_query = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    products_related = db.Column(db.String(255))