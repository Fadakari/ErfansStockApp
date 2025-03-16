from datetime import datetime
from aplication import db, login_manager
from datetime import datetime#-
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    products = db.relationship('Product', backref='owner', lazy=True)
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy='dynamic')#+
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy='dynamic')#+

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    products = db.relationship('Product', backref='category', lazy=True)

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
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)#-
    messages = db.relationship('Message', backref='product', lazy='dynamic')#+
    is_promoted = db.Column(db.Boolean, default=False)
#+
class Message(db.Model):#+
    id = db.Column(db.Integer, primary_key=True)#+
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)#+
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)#+
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)#+
    content = db.Column(db.Text, nullable=False)#+
    created_at = db.Column(db.DateTime, default=datetime.utcnow)#+
