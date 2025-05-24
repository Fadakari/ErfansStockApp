from aplication import scheduler, db, app
from models import Product
from datetime import datetime, timedelta
import logging

@scheduler.task('interval', id='check_pending_products', hours=1)
def check_pending_products():
    with app.app_context():
        logging.info("✅ اجرای تسک: بررسی وضعیت محصولات در انتظار تایید")

        now = datetime.utcnow()
        one_day_ago = now - timedelta(hours=1)

        # بررسی محصولات منقضی‌شده (promoted_until گذشته)
        expired = Product.query.filter(
            Product.status == 'published',
            Product.promoted_until != None,
            Product.promoted_until < now
        ).all()

        for product in expired:
            logging.info(f"⏳ محصول {product.id} منقضی شده! تغییر وضعیت به pending")
            product.status = 'pending'

        # بررسی محصولات pending قدیمی (که promoted_until ندارن)
        products = Product.query.filter_by(status='pending').filter(Product.promoted_until == None).all()

        for product in products:
            logging.info(f"Checking product ID: {product.id}, Created at: {product.created_at}")

            if product.created_at < one_day_ago:
                user_products_count = Product.query.filter_by(user_id=product.user_id, status='published').count()
                logging.info(f"User {product.user_id} has {user_products_count} published products")

                if user_products_count >= 5:
                    logging.info(f"Changing product {product.id} status to 'published'")
                    product.status = 'published'
                else:
                    logging.info(f"Changing product {product.id} status to 'awaiting_payment'")
                    product.status = 'awaiting_payment'

        db.session.commit()
