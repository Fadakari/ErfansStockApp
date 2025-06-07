import os
import logging
from dotenv import load_dotenv
from flask import Flask, render_template, Response, url_for
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from sqlalchemy.orm import DeclarativeBase
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_apscheduler import APScheduler  # ✅ اضافه شده
import redis
from flask_cors import CORS
from datetime import date
from flask_jwt_extended import JWTManager




# بارگذاری متغیرهای محیطی از .env
load_dotenv()
print("loaded DB URL:", os.environ.get("DATABASE_URL"))

# اتصال به Redis
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)

# مقداردهی به Limiter
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="redis://localhost:6379/0"
)

# مقداردهی به افزونه‌ها
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
scheduler = APScheduler()  # ✅ اضافه شده


# تعریف کلاس پایه برای ORM
class Base(DeclarativeBase):
    pass


logging.basicConfig(
    level=logging.DEBUG,  # یا logging.INFO برای لاگ کمتر
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.StreamHandler(),              # نمایش در ترمینال
        logging.FileHandler("error.log", encoding='utf-8')  # ذخیره در فایل error.log
    ]
)


def create_app():
    app = Flask(__name__)
    limiter.init_app(app)
    CORS(app, supports_credentials=True, resources={r"/*": {"origins": [
        r"http://localhost:\d+",
        "http://localhost",
        r"http://127.0.0.1:\d+",
        "capacitor://localhost",
        "https://stockdivar.ir",
    ]}})
       
    # بارگذاری کلید مخفی و اطلاعات دیتابیس از محیط
    app.secret_key = os.environ.get("SECRET_KEY", "کلید_پیش‌فرض_اما_غیر_امن")
    app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "your-super-secret-and-strong-jwt-key")
    app.config["ZIBAL_MERCHANT"] = os.environ.get("ZIBAL_MERCHANT")
    app.config["ZIBAL_CALLBACK_URL"] = os.environ.get("ZIBAL_CALLBACK_URL")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
    app.config["SERVER_NAME"] = "stockdivar.ir"
    app.config["PREFERRED_URL_SCHEME"] = "https"
    app.config["BAZAR_CLIENT_ID"] = os.getenv("BAZAR_CLIENT_ID")
    app.config["BAZAR_CLIENT_SECRET"] = os.getenv("BAZAR_CLIENT_SECRET")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config["AVALAI_API_KEY"] = os.environ.get("AVALAI_API_KEY")
    app.config["AVALAI_CHAT_MODEL"] = os.environ.get("AVALAI_CHAT_MODEL")
    app.config["BAZAAR_MERCHANT_ID"] = os.environ.get("BAZAAR_MERCHANT_ID")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    print("ZIBAL_MERCHANT:", app.config["ZIBAL_MERCHANT"])

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

    if os.environ.get("FLASK_RUN_FROM_CLI") == "true":
        scheduler.init_app(app)

    # ثبت بلوپرینت‌ها
    from routes import bp as html_routes
    from all_in_one_routes import bp as api_routes
    app.register_blueprint(html_routes)
    app.register_blueprint(api_routes, url_prefix="/api")

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404
    


    @app.route('/sitemap.xml')
    def sitemap():
        pages = []
        lastmod = date.today().isoformat()

        for rule in app.url_map.iter_rules():
            excluded_routes = [
                '/logout', '/verify_login', '/init-categories',
                '/payment/callback', '/test/expire-soon', '/get_new_messages',
                '/ionicApp-server', '/sitemap.xml', '/my_store', '/chatbot', '/bazaar-login', '/bazaar-callback', '/bazaar-auth', '/verify-phone-change'
            ]
            # حذف APIها و مسیرهای دارای پارامتر
            if "GET" in rule.methods and len(rule.arguments) == 0 and not rule.rule.startswith("/api") and rule.rule not in excluded_routes:
                try:
                    url = url_for(rule.endpoint, _external=True)
                    priority = "1.0" if rule.rule == "/" else "0.8"
                    pages.append({
                        "loc": url,
                        "lastmod": lastmod,
                        "priority": priority
                    })
                except Exception as e:
                    logging.warning(f"خطا در پردازش مسیر {rule}: {e}")

        sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        sitemap_xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

        for page in pages:
            sitemap_xml += f"""  <url>
        <loc>{page['loc']}</loc>
        <lastmod>{page['lastmod']}</lastmod>
        <changefreq>weekly</changefreq>
        <priority>{page['priority']}</priority>
        </url>\n"""

        sitemap_xml += '</urlset>'

        return Response(sitemap_xml, mimetype='application/xml')

    # ایجاد جداول دیتابیس در صورت نیاز
    with app.app_context():
        try:
            db.create_all()
            logging.info("Database tables created successfully")
        except Exception as e:
            logging.error(f"Error creating database tables: {str(e)}")

    return app

app = create_app()


# اجرای اپلیکیشن
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    app.run(debug=True)
