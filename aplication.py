import os
import logging
from dotenv import load_dotenv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from sqlalchemy.orm import DeclarativeBase
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import redis

# بارگذاری متغیرهای محیطی از .env
load_dotenv()

# اتصال به Redis
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)

# مقداردهی به Limiter
limiter = Limiter(get_remote_address, app=None, storage_uri="redis://localhost:6379/0")

# مقداردهی به افزونه‌ها
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

# تعریف کلاس پایه برای ORM
class Base(DeclarativeBase):
    pass

def create_app():
    app = Flask(__name__)

    # بارگذاری کلید مخفی و اطلاعات دیتابیس از محیط
    app.secret_key = os.environ.get("SECRET_KEY", "کلید_پیش‌فرض_اما_غیر_امن")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # تنظیمات آپلود فایل
    app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB

    # استفاده از Redis برای Limiter بدون استفاده از storage
    limiter.init_app(app)

    # ساخت پوشه آپلود در صورت نبود
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # مقداردهی به افزونه‌ها
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "main.login"

    # ثبت بلوپرینت‌ها
    from routes import bp
    app.register_blueprint(bp)

    # ایجاد جداول دیتابیس در صورت نیاز
    with app.app_context():
        try:
            db.create_all()
            logging.info("Database tables created successfully")
        except Exception as e:
            logging.error(f"Error creating database tables: {str(e)}")

    return app

# اجرای اپلیکیشن
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    app = create_app()
    app.run(debug=True)
