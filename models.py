from datetime import datetime, timedelta
from aplication import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from enum import Enum
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, TextAreaField, SelectField, SubmitField
from wtforms.validators import Email, DataRequired, Length


bookmarks = db.Table('bookmarks',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('product_id', db.Integer, db.ForeignKey('product.id'), primary_key=True)
)


blocked_users = db.Table('blocked_users',
    db.Column('blocker_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('blocked_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)


job_applications = db.Table('job_applications',
    db.Column('job_listing_id', db.Integer, db.ForeignKey('job_listing.id'), primary_key=True),
    db.Column('job_profile_id', db.Integer, db.ForeignKey('job_profile.id'), primary_key=True),
    db.Column('application_date', db.DateTime, default=datetime.utcnow)
)


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
    saved_products = db.relationship('Product', secondary=bookmarks, lazy='dynamic', backref=db.backref('saved_by_users', lazy=True))
    bazaar_account_id = db.Column(db.String(128), unique=True, nullable=True)
    bazaar_access_token = db.Column(db.Text)
    bazaar_refresh_token = db.Column(db.Text, nullable=True)
    products = db.relationship('Product', back_populates='owner', lazy='dynamic', cascade="all, delete-orphan")
    is_admin = db.Column(db.Boolean, default=False)
    fcm_token = db.Column(db.String(255), nullable=True, unique=True)
    is_banned = db.Column(db.Boolean, default=False, nullable=False)
    ban_reason = db.Column(db.String(255), nullable=True)
    sessions = db.relationship('UserSession', backref='user', lazy='dynamic', cascade="all, delete-orphan")

    # Reports, Messages, Conversations, etc.
    reports_filed = db.relationship('Report', back_populates='reporter', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='Report.reporter_id')
    chat_interactions = db.relationship('ChatBotInteraction', back_populates='user', lazy='dynamic', cascade="all, delete-orphan")
    job_listings = db.relationship('JobListing', back_populates='owner', lazy='dynamic', cascade="all, delete-orphan")
    job_profile = db.relationship('JobProfile', back_populates='owner', uselist=False, cascade="all, delete-orphan")
    conversations_as_user1 = db.relationship('Conversation', foreign_keys='Conversation.user1_id', back_populates='user1', lazy='dynamic', cascade="all, delete-orphan")
    conversations_as_user2 = db.relationship('Conversation', foreign_keys='Conversation.user2_id', back_populates='user2', lazy='dynamic', cascade="all, delete-orphan")
    messages_sent = db.relationship('Message', foreign_keys='Message.sender_id', back_populates='sender', lazy='dynamic', cascade="all, delete-orphan")
    messages_received = db.relationship('Message', foreign_keys='Message.receiver_id', back_populates='receiver', lazy='dynamic', cascade="all, delete-orphan")
    sent_user_reports = db.relationship('UserReport', foreign_keys='UserReport.reporter_id', back_populates='reporter', lazy='dynamic', cascade="all, delete-orphan")
    received_user_reports = db.relationship('UserReport', foreign_keys='UserReport.reported_id', back_populates='reported', lazy='dynamic', cascade="all, delete-orphan")
    job_listing_reports_filed = db.relationship('JobListingReport', back_populates='reporter', lazy='dynamic', cascade="all, delete-orphan")
    job_profile_reports_filed = db.relationship('JobProfileReport', back_populates='reporter', lazy='dynamic', cascade="all, delete-orphan")

    blocked = db.relationship(
        'User', secondary=blocked_users,
        primaryjoin=(blocked_users.c.blocker_id == id),
        secondaryjoin=(blocked_users.c.blocked_id == id),
        backref=db.backref('blocked_by', lazy='dynamic'),
        lazy='dynamic'
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def block(self, user):
        if not self.has_blocked(user):
            self.blocked.append(user)
    
    def unblock(self, user):
        if self.has_blocked(user):
            self.blocked.remove(user)
            
    def has_blocked(self, user):
        return self.blocked.filter(blocked_users.c.blocked_id == user.id).count() > 0
    

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
    parent_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
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
    images = db.relationship('ProductImage', backref='product', lazy=True, cascade="all, delete-orphan")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    promoted_until = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_promoted = db.Column(db.Boolean, default=False)
    address = db.Column(db.String(1000), nullable=False)
    postal_code = db.Column(db.String(20), nullable=True)
    product_type = db.Column(db.Enum(ProductType), nullable=False)
    views = db.Column(db.Integer, default=0)
    owner = db.relationship('User', back_populates='products', lazy=True)
    status = db.Column(db.String(20), default='pending')
    expires_at = db.Column(db.DateTime, nullable=True)
    brand = db.Column(db.String(100), nullable=True)
    is_electric = db.Column(db.Boolean, default=False)
    is_cordless = db.Column(db.Boolean, default=False)
    is_pneumatic = db.Column(db.Boolean, default=False)

    is_body_only = db.Column(db.Boolean, default=False)
    body_only_description = db.Column(db.String(255), nullable=True)

    is_chat_only = db.Column(db.Boolean, default=False)
    contact_phone = db.Column(db.String(15), nullable=True)
    reports = db.relationship('Report', backref='product', cascade='all, delete-orphan', lazy=True)

    def __init__(self, name, description, price, image_path, user_id, category_id, 
                 promoted_until=None, address=None, postal_code=None, product_type=None, 
                 views=0, status='pending', expires_at=None, brand=None,
                 is_electric=False, is_cordless=False, is_pneumatic=False,
                 is_body_only=False, body_only_description=None,
                 is_chat_only=False, contact_phone=None):
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
        self.views = views
        self.status = status
        self.expires_at = expires_at if expires_at else datetime.utcnow() + timedelta(days=30)
        self.brand = brand
        self.is_electric = is_electric
        self.is_cordless = is_cordless
        self.is_pneumatic = is_pneumatic
        self.is_body_only = is_body_only
        self.body_only_description = body_only_description
        self.is_chat_only = is_chat_only
        self.contact_phone = contact_phone


        if product_type:
            print(f"Raw Product Type Before Enum Conversion: {product_type}")
            if isinstance(product_type, str) and product_type in ProductType.__members__:
                self.product_type = ProductType[product_type]
            elif isinstance(product_type, ProductType):
                self.product_type = product_type
            else:
                self.product_type = None
            print(f"Final Product Type in __init__: {self.product_type}")
        else:
            self.product_type = None



class ProductImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image_path = db.Column(db.String(255), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)



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
    category_id = SelectField('Category', choices=[], coerce=int)
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
        ('AEG', 'AEG'),
        ('wurth', 'wurth'),
        ('wiha', 'wiha'),
        ('genius', 'genius'),
        ('sparky', 'sparky'),
        ('ronix', 'ronix'),
        ('tosan', 'tosan'),
        ('arva', 'arva'),
        ('kenzax', 'kenzax'),
        ('unknown', 'unknown')
    ], validators=[DataRequired()])
    submit = SubmitField('Add Product')


class EditProfileForm(FlaskForm):
    username = StringField('نام کاربری', validators=[DataRequired()])
    email = StringField('ایمیل', validators=[DataRequired(), Email()])
    phone = StringField('شماره تماس جدید', validators=[Length(min=10, max=15)])
    submit = SubmitField('ذخیره تغییرات')


class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user2_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    user1 = db.relationship('User', foreign_keys=[user1_id], back_populates='conversations_as_user1')
    user2 = db.relationship('User', foreign_keys=[user2_id], back_populates='conversations_as_user2')

    messages = db.relationship('Message', back_populates='conversation', cascade="all, delete-orphan")



class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'))
    replied_to_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=True)
    file_path = db.Column(db.String(255), nullable=True)
    sender = db.relationship('User', foreign_keys=[sender_id], back_populates='messages_sent')
    receiver = db.relationship('User', foreign_keys=[receiver_id], back_populates='messages_received')
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    conversation = db.relationship('Conversation', back_populates='messages')
    
    replied_to = db.relationship('Message', remote_side=[id], backref=db.backref('replies', lazy=True), uselist=False)



class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reporter = db.relationship('User', back_populates='reports_filed')


class UserReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reported_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=True)
    reason = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reporter = db.relationship('User', foreign_keys=[reporter_id], back_populates='sent_user_reports')
    reported = db.relationship('User', foreign_keys=[reported_id], back_populates='received_user_reports')
    conversation = db.relationship('Conversation', backref='user_reports')


class ChatBotInteraction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user_query = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    products_related = db.Column(db.String(255))
    user = db.relationship('User', back_populates='chat_interactions')




class CooperationType(Enum):
    FULL_TIME = 'تمام وقت'
    PART_TIME = 'پاره وقت'
    REMOTE = 'دورکاری'
    PROJECT = 'پروژه‌ای'
    INTERNSHIP = 'کارآموزی'

class SalaryType(Enum):
    MONTHLY = 'ماهانه'
    HOURLY = 'ساعتی'
    DAILY = 'روزانه'
    COMMISSION = 'پورسانتی'
    NEGOTIABLE = 'توافقی'

class MilitaryStatus(Enum):
    NOT_APPLICABLE = 'مشمول نیستم'
    COMPLETED = 'کارت پایان خدمت'
    EXEMPT = 'کارت معافیت'
    PENDING = 'در حال خدمت'

class MaritalStatus(Enum):
    SINGLE = 'مجرد'
    MARRIED = 'متاهل'

class EducationLevel(Enum):
    CYCLE = 'سیکل'
    DIPLOMA = 'دیپلم'
    ASSOCIATE = 'فوق دیپلم'
    BACHELOR = 'کارشناسی'
    MASTER = 'کارشناسی ارشد'
    PHD = 'دکترا'



class JobListing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    profile_picture = db.Column(db.String(100), nullable=True, default='default.jpg')
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    benefits = db.Column(db.Text, nullable=True)
    cooperation_type = db.Column(db.Enum(CooperationType), nullable=False)
    salary_type = db.Column(db.Enum(SalaryType), nullable=False)
    salary_min = db.Column(db.Integer, nullable=True)
    salary_max = db.Column(db.Integer, nullable=True)
    has_insurance = db.Column(db.Boolean, default=False)
    military_status_required = db.Column(db.Enum(MilitaryStatus), nullable=True)
    is_remote_possible = db.Column(db.Boolean, default=False)
    working_hours = db.Column(db.String(100), nullable=True)
    location = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    
    owner = db.relationship('User', back_populates='job_listings')

    applicants = db.relationship(
        'JobProfile',
        secondary=job_applications,
        back_populates='applied_to_listings',
        lazy='dynamic'
    )


class JobProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    profile_picture = db.Column(db.String(100), nullable=True, default='default.jpg')
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    portfolio_links = db.Column(db.Text, nullable=True)
    resume_path = db.Column(db.String(255), nullable=True)
    contact_phone = db.Column(db.String(15), nullable=False)
    contact_email = db.Column(db.String(120), nullable=True)
    marital_status = db.Column(db.Enum(MaritalStatus), nullable=True)
    military_status = db.Column(db.Enum(MilitaryStatus), nullable=True)
    location = db.Column(db.String(200), nullable=True)
    birth_date = db.Column(db.Date, nullable=True)
    requested_salary_min = db.Column(db.Integer, nullable=True)
    requested_salary_max = db.Column(db.Integer, nullable=True)
    reports = db.relationship('JobProfileReport', backref='job_profile', cascade='all, delete-orphan', lazy=True)
    education_status = db.Column(db.String(50), nullable=True)
    highest_education_level = db.Column(db.Enum(EducationLevel), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    owner = db.relationship('User', back_populates='job_profile')
    work_experiences = db.relationship('WorkExperience', backref='profile', lazy='dynamic', cascade="all, delete-orphan")

    applied_to_listings = db.relationship(
        'JobListing',
        secondary=job_applications,
        back_populates='applicants',
        lazy='dynamic'
    )


class WorkExperience(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey('job_profile.id'), nullable=False)
    company_name = db.Column(db.String(100), nullable=False)
    job_title = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.String(20), nullable=True)
    end_date = db.Column(db.String(20), nullable=True)
    description = db.Column(db.Text, nullable=True)


class JobListingReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_listing_id = db.Column(db.Integer, db.ForeignKey('job_listing.id'), nullable=False)
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reporter = db.relationship('User', back_populates='job_listing_reports_filed')

class JobProfileReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_profile_id = db.Column(db.Integer, db.ForeignKey('job_profile.id'), nullable=False)
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reporter = db.relationship('User', back_populates='job_profile_reports_filed')




class CategoryView(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('category_views', lazy='dynamic'))
    category = db.relationship('Category', backref=db.backref('views', lazy='dynamic'))



class SearchHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    search_term = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('search_history', lazy='dynamic'))


class UserSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    session_token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    login_time = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    def __repr__(self):
        return f'<UserSession {self.id} for User {self.user_id}>'



class TicketStatus(Enum):
    OPEN = 'باز'
    USER_REPLIED = 'پاسخ کاربر'
    ADMIN_REPLIED = 'پاسخ داده شد'
    CLOSED = 'بسته شده'

# Add the new models at the end of the file
class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    status = db.Column(db.Enum(TicketStatus), default=TicketStatus.OPEN, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('tickets', lazy='dynamic', cascade="all, delete-orphan"))
    messages = db.relationship('TicketMessage', backref='ticket', lazy='dynamic', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Ticket {self.id} - {self.subject}>'

class TicketMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # The user who sent the message
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    file_path = db.Column(db.String(255), nullable=True) # For attachments

    sender = db.relationship('User', backref=db.backref('ticket_messages', lazy='dynamic'))

    def __repr__(self):
        return f'<TicketMessage {self.id} for Ticket {self.ticket_id}>'