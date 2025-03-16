import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from sqlalchemy.orm import DeclarativeBase

app = Flask(__name__)
app.secret_key = "یک_کلید_امن_و_تصادفی"  # مقدار دلخواه ولی امن

# بقیه‌ی کدهای Flask مثل مسیرها (routes) اینجا قرار می‌گیرند.

if __name__ == "__main__":
    app.run(debug=True)





# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

# Initialize extensions without app
db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()



def create_app():
    # Create the app
    app = Flask(__name__)
    app.secret_key = os.environ.get("SESSION_SECRET", "B@h702600$")

    # Configure the database
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///C:/Users/iTeck/pythone-app/database.db"
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