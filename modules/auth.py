from flask import request, jsonify
from functools import wraps
import jwt
from datetime import datetime, timedelta, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Импорт центрального модуля
from modules.core import get_app, get_db, get_bcrypt

# Получаем основной экземпляр Flask и расширения из центрального модуля
app = get_app()
db = get_db()
bcrypt = get_bcrypt()

# Импорт модели User из modules.user
from modules.user import User

# Функции аутентификации
def create_local_jwt(user_id):
    payload = {'iat': datetime.now(timezone.utc), 'exp': datetime.now(timezone.utc) + timedelta(days=1), 'sub': str(user_id)}
    token = jwt.encode(payload, app.config['JWT_SECRET_KEY'], algorithm="HS256")
    return token

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"message": "Auth required"}), 401
        try:
            local_token = auth_header.split(" ")[1]
            payload = jwt.decode(local_token, app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
            user = db.session.get(User, int(payload['sub']))
            if not user or user.role != 'ADMIN':
                return jsonify({"message": "Forbidden"}), 403
            kwargs['current_admin'] = user
        except Exception:
            return jsonify({"message": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated_function

def get_user_from_token():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    try:
        local_token = auth_header.split(" ")[1]
        payload = jwt.decode(local_token, app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
        user = db.session.get(User, int(payload['sub']))
        return user
    except Exception:
        return None