import sys
sys.path.append('/var/www/myproject2')  # مسیر دقیق تا جایی که application.py هست

import os
os.environ["FLASK_RUN_FROM_CLI"] = "true"

from aplication import create_app, db, scheduler  # اینجا رو تغییر دادیم
import tasks

app = create_app()

with app.app_context():
    scheduler.init_app(app)
    scheduler.start()
    print("✅ Scheduler started.")

    import time
    while True:
        time.sleep(60)
