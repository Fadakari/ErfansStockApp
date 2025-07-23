from aplication import scheduler, db, app
from models import Product
from datetime import datetime, timedelta
import logging

@scheduler.task('interval', id='check_pending_products', hours=1)
def check_pending_products():

    with app.app_context():
        logging.info("✅ اجرای تسک: بررسی وضعیت محصولات")

        now = datetime.utcnow()

        expired_promotions = Product.query.filter(
            Product.promoted_until != None,
            Product.promoted_until < now
        ).all()

        for product in expired_promotions:
            logging.info(f"⏳ نردبان محصول {product.id} منقضی شده! حذف نردبان و باقی ماندن در حالت انتشار.")
            
            product.promoted_until = None
        
        one_hour_ago = now - timedelta(hours=1)
        pending_products = Product.query.filter_by(status='pending').filter(Product.promoted_until == None).all()

        for product in pending_products:
            if product.created_at < one_hour_ago:
                user_products_count = Product.query.filter_by(user_id=product.user_id, status='published').count()
                
                if user_products_count >= 5:
                    product.status = 'published'
                    logging.info(f"محصول {product.id} به دلیل داشتن بیش از ۵ محصول، رایگان منتشر شد.")
                else:
                    product.status = 'awaiting_payment'
                    logging.info(f"محصول {product.id} در وضعیت آماده پرداخت قرار گرفت.")

        db.session.commit()