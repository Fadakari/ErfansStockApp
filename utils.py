import os
import logging
from werkzeug.utils import secure_filename
from flask import current_app

logging.basicConfig(level=logging.DEBUG)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_image(file, filename=None):
    """
    Simple file save function without image processing
    """
    try:
        if not file or not file.filename:
            logging.warning("No file provided")
            return None

        if not allowed_file(file.filename):
            logging.warning(f"File type not allowed: {file.filename}")
            return None

        filename = filename or secure_filename(file.filename)  # ← این تغییر مهم
        upload_dir = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_dir, exist_ok=True)

        file_path = os.path.join(upload_dir, filename)
        file.save(file_path)
        logging.info(f"File saved successfully: {file_path}")

        return filename

    except Exception as e:
        logging.error(f"Error saving file: {str(e)}")
        return None