from aplication import create_app, db
from models import User

app = create_app()
app.app_context().push()

# اطلاعات جدید برای بروزرسانی کاربر
phone = "09123456789"  # شماره تلفن برای جستجو
new_username = "هیلتی حیدری"
new_email = "erfan85@gmail.com"
new_national_id = "0110826817"
new_password = "erfan43154315"
is_admin = True

# پیدا کردن کاربر
user = User.query.filter_by(phone=phone).first()

if user:
    user.username = new_username
    user.email = new_email
    user.national_id = new_national_id
    user.set_password(new_password)
    user.is_admin = is_admin

    db.session.commit()
    print(f"کاربر {phone} succesfuly.")
else:
    print("❌ کاربری با این شماره پیدا نشد.")


