import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from sqlalchemy.orm import DeclarativeBase

# تنظیمات برنامه
app = Flask(__name__)
app.secret_key = "یک_کلید_امن_و_تصادفی"

# تنظیمات بانک اطلاعاتی
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql://user:password@localhost/dbname"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False  # غیرفعال کردن هشدارهای اضافی

# کلاس پایه برای ORM
class Base(DeclarativeBase):
    pass


# مقداردهی به `db` بعد از مقداردهی `app`
db = SQLAlchemy(app, model_class=Base)

# مقداردهی `LoginManager`
login_manager = LoginManager()
login_manager.init_app(app)

# مقداردهی `Flask-Migrate`
migrate = Migrate(app, db)

# تنظیمات درگاه پرداخت
app.config["ZIBAL_MERCHANT"] = "65717f98c5d2cb000c3603da"
app.config["ZIBAL_CALLBACK_URL"] = "http://localhost:5000/payment/callback"

# ایمپورت و ثبت Blueprints بعد از مقداردهی `app`
from routes import bp
app.register_blueprint(bp)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# اجرای اپلیکیشن فقط در حالت اجرا به عنوان main
if __name__ == "__main__":
    app.run(debug=True)




def create_app():
    # Create the app
    app = Flask(__name__)
    app.secret_key = os.environ.get("SESSION_SECRET", "B@h702600$")

    # Configure the database
    app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+mysqlconnector://root:B%40h702600%24@localhost/my_database"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    # Configure upload settings
    app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file size
    # Ensure upload directory exists
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    logging.info(f"Upload folder created at: {app.config['UPLOAD_FOLDER']}")
    logging.info(f"Database URL configured: {app.config['SQLALCHEMY_DATABASE_URI']}")
    # Initialize extensions with app
    db.init_app(app)
    migrate = Migrate(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "main.login"
    with app.app_context():
        # Import and register blueprint
        from routes import bp
        app.register_blueprint(bp)
        # Create all database tables
        try:
            db.create_all()  # This should come after app.init_app()
            logging.info("Database tables created successfully")
        except Exception as e:
            logging.error(f"Error creating database tables: {str(e)}")
    return app

# Create the app instance
app = create_app()