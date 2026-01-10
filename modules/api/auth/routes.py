"""
API эндпоинты авторизации

- POST /api/public/register - Регистрация
- POST /api/public/login - Вход
- POST /api/public/forgot-password - Сброс пароля
- POST /api/public/verify-email - Подтверждение email
- POST /api/public/resend-verification - Повторная отправка
- POST /api/public/telegram-login - Вход через Telegram
"""

from flask import request, jsonify, render_template
from datetime import datetime, timedelta, timezone
import random
import string
import threading
import requests
import json
import os

from modules.core import get_app, get_db, get_bcrypt, get_fernet, get_mail, get_cache, get_limiter
from modules.auth import create_local_jwt
from modules.models.user import User
from modules.models.system import SystemSetting
from modules.models.referral import ReferralSetting
from modules.models.branding import BrandingSetting
from modules.models.bot_config import BotConfig

app = get_app()
db = get_db()
bcrypt = get_bcrypt()
fernet = get_fernet()
mail = get_mail()
cache = get_cache()
limiter = get_limiter()


def generate_referral_code(user_id):
    """Генерация реферального кода"""
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
    return f"REF-{user_id}-{random_part}"


def get_remnawave_headers(additional_headers=None):
    """Получение заголовков для RemnaWave API"""
    headers = {}
    cookies = {}
    
    ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
    REMNAWAVE_COOKIES_STR = os.getenv("REMNAWAVE_COOKIES", "")
    
    if ADMIN_TOKEN:
        headers["Authorization"] = f"Bearer {ADMIN_TOKEN}"
    
    if REMNAWAVE_COOKIES_STR:
        try:
            cookies = json.loads(REMNAWAVE_COOKIES_STR)
        except json.JSONDecodeError:
            pass
    
    if additional_headers:
        headers.update(additional_headers)
    
    return headers, cookies


def send_email_in_background(app_context, recipient, subject, html_body):
    """Отправка email в фоновом режиме"""
    with app_context:
        try:
            from flask import current_app
            from flask_mail import Message
            
            mail_server = current_app.config.get('MAIL_SERVER')
            mail_username = current_app.config.get('MAIL_USERNAME')
            mail_password = current_app.config.get('MAIL_PASSWORD')
            
            if not all([mail_server, mail_username, mail_password]):
                app.logger.warning(f"[EMAIL] Mail not configured - MAIL_SERVER: {bool(mail_server)}, MAIL_USERNAME: {bool(mail_username)}, MAIL_PASSWORD: {bool(mail_password)}")
                return
            
            msg = Message(subject, recipients=[recipient])
            msg.html = html_body
            mail.send(msg)
            app.logger.info(f"[EMAIL] ✓ Sent to {recipient}")
            
        except Exception as e:
            app.logger.error(f"[EMAIL] ❌ Error sending email to {recipient}: {e}", exc_info=True)


def get_system_settings():
    """Получить системные настройки"""
    return SystemSetting.query.first()


def create_system_settings():
    """Создать настройки по умолчанию"""
    settings = SystemSetting(default_language='ru', default_currency='uah')
    db.session.add(settings)
    db.session.commit()
    return settings


def get_referral_settings():
    """Получить настройки рефералов"""
    return ReferralSetting.query.first()


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.route('/api/public/register', methods=['POST'])
@limiter.limit("5 per hour")
def public_register():
    """Регистрация нового пользователя"""
    data = request.json
    email, password, ref_code = data.get('email'), data.get('password'), data.get('ref_code')
    telegram_id = data.get('telegram_id')  # Опционально: для связи с Telegram аккаунтом

    if not isinstance(email, str) or not isinstance(password, str):
        return jsonify({"message": "Неверный формат ввода"}), 400
    if not email or not password:
        return jsonify({"message": "Требуется адрес электронной почты и пароль"}), 400

    email = email.strip().lower()

    # Проверяем существование по email
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({"message": "User exists"}), 400
    
    # Если указан telegram_id, проверяем, не занят ли он
    if telegram_id:
        telegram_id_str = str(telegram_id)
        existing_telegram_user = User.query.filter_by(telegram_id=telegram_id_str).first()
        if existing_telegram_user:
            return jsonify({"message": "Telegram account already registered"}), 400

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    clean_username = email.replace("@", "_").replace(".", "_")

    referrer, bonus_days_new = None, 0
    if ref_code and isinstance(ref_code, str):
        referrer = User.query.filter_by(referral_code=ref_code).first()
        if referrer:
            s = get_referral_settings()
            bonus_days_new = s.invitee_bonus_days if s else 7

    expire_date = (datetime.now(timezone.utc) + timedelta(days=bonus_days_new)).isoformat()

    try:
        headers, cookies = get_remnawave_headers()
        API_URL = os.getenv('API_URL')
        
        # Сначала проверяем, существует ли пользователь в RemnaWave по email
        existing_remnawave_user = None
        try:
            # URL-encode email для безопасной передачи
            import urllib.parse
            encoded_email = urllib.parse.quote(email, safe='')
            check_resp = requests.get(
                f"{API_URL}/api/users/by-email/{encoded_email}",
                headers=headers,
                cookies=cookies,
                timeout=15
            )
            if check_resp.status_code == 200:
                check_data = check_resp.json()
                # API может вернуть response с пользователем или массив пользователей
                if check_data.get('response'):
                    existing_remnawave_user = check_data['response']
                    if isinstance(existing_remnawave_user, list) and len(existing_remnawave_user) > 0:
                        existing_remnawave_user = existing_remnawave_user[0]
                print(f"Found existing user in RemnaWave by email: {existing_remnawave_user.get('uuid') if existing_remnawave_user else 'None'}")
        except Exception as e:
            print(f"Error checking existing user by email: {e}")
        
        # Если пользователь существует в RemnaWave - используем его UUID
        if existing_remnawave_user and existing_remnawave_user.get('uuid'):
            remnawave_uuid = existing_remnawave_user.get('uuid')
            print(f"Using existing RemnaWave user UUID: {remnawave_uuid}")
        else:
            # Пользователь не найден - создаём нового
            payload_create = {
                "email": email, "password": password, "username": clean_username,
                "expireAt": expire_date,
                "activeInternalSquads": [os.getenv("DEFAULT_SQUAD_ID")] if referrer else []
            }

            resp = requests.post(f"{API_URL}/api/users", headers=headers, cookies=cookies, json=payload_create)
            resp.raise_for_status()
            remnawave_uuid = resp.json().get('response', {}).get('uuid')

        if not remnawave_uuid:
            return jsonify({"message": "Provider Error"}), 500

        verif_token = ''.join(random.choices(string.ascii_letters + string.digits, k=50))
        sys_settings = get_system_settings() or create_system_settings()
        
        if not sys_settings:
            print(f"Register Error: Failed to get or create system settings")
            return jsonify({"message": "Internal Server Error"}), 500

        new_user = User(
            email=email, password_hash=hashed_password, remnawave_uuid=remnawave_uuid,
            telegram_id=str(telegram_id) if telegram_id else None,  # Связываем с Telegram, если указан
            referrer_id=referrer.id if referrer else None, is_verified=False,
            verification_token=verif_token, created_at=datetime.now(timezone.utc),
            preferred_lang=sys_settings.default_language,
            preferred_currency=sys_settings.default_currency
        )
        db.session.add(new_user)
        db.session.flush()
        new_user.referral_code = generate_referral_code(new_user.id)
        db.session.commit()
        
        # Отправляем уведомление админам о новом пользователе
        try:
            from modules.notifications import notify_new_user
            notify_new_user(new_user, "website")
        except Exception as e:
            print(f"Error sending new user notification: {e}")

        # Отправка email
        try:
            your_server_ip = os.getenv('YOUR_SERVER_IP') or os.getenv('YOUR_SERVER_IP_OR_DOMAIN')
            if your_server_ip:
                your_server_ip = your_server_ip.strip()
                if not your_server_ip.startswith(('http://', 'https://')):
                    your_server_ip = f"https://{your_server_ip}"
            else:
                your_server_ip = "https://testpanel.stealthnet.app"

            url = f"{your_server_ip}/verify?token={verif_token}"
            # Получаем branding и service_name для шаблона
            branding = BrandingSetting.query.first()
            bot_config = BotConfig.query.first()
            service_name = bot_config.service_name if bot_config else (branding.site_name if branding else "StealthNET")
            html = render_template('email_verification.html', 
                                 verification_url=url,
                                 branding=branding,
                                 service_name=service_name)
            threading.Thread(target=send_email_in_background, args=(app.app_context(), email, "Подтвердите email", html)).start()
        except Exception as e:
            print(f"Error preparing email: {e}")
            # Не прерываем регистрацию из-за ошибки email

        # Бонус рефереру
        if referrer:
            s = get_referral_settings()
            days = s.referrer_bonus_days if s else 7
            headers, cookies = get_remnawave_headers()
            resp = requests.get(f"{os.getenv('API_URL')}/api/users/{referrer.remnawave_uuid}", headers=headers, cookies=cookies)
            if resp.ok:
                live_data = resp.json().get('response', {})
                curr = datetime.fromisoformat(live_data.get('expireAt'))
                new_exp = max(datetime.now(timezone.utc), curr) + timedelta(days=days)
                requests.patch(f"{os.getenv('API_URL')}/api/users",
                            headers={"Content-Type": "application/json", **headers},
                            json={"uuid": referrer.remnawave_uuid, "expireAt": new_exp.isoformat()})
                cache.delete(f'live_data_{referrer.remnawave_uuid}')

        return jsonify({"message": "Регистрация прошла успешно. Проверьте email."}), 201

    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Provider error"}), 500
    except Exception as e:
        print(f"Register Error: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({"message": "Internal Server Error"}), 500


@app.route('/api/public/login', methods=['POST'])
@limiter.limit("10 per minute")
def client_login():
    """Вход пользователя"""
    data = request.json
    email, password = data.get('email'), data.get('password')

    if not isinstance(email, str) or not isinstance(password, str):
        return jsonify({"message": "Invalid input"}), 400

    try:
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({"message": "Invalid credentials"}), 401
        
        # Если password_hash пустой, но есть telegram_id, это пользователь из бота
        # Разрешаем вход, но рекомендуем использовать Telegram Login Widget
        if not user.password_hash or user.password_hash == '':
            if user.telegram_id:
                # Пользователь зарегистрирован через бота, но может войти на сайте
                # (например, через Telegram Login Widget или если пароль был установлен позже)
                return jsonify({
                    "message": "This account uses Telegram login. Please use Telegram Login Widget.",
                    "code": "TELEGRAM_ACCOUNT",
                    "telegram_id": user.telegram_id
                }), 401
            else:
                return jsonify({"message": "This account uses Telegram login"}), 401
        
        if not bcrypt.check_password_hash(user.password_hash, password):
            return jsonify({"message": "Invalid credentials"}), 401
        if not user.is_verified:
            return jsonify({"message": "Email не подтверждён", "code": "NOT_VERIFIED"}), 403
        
        # Проверяем блокировку аккаунта
        if getattr(user, 'is_blocked', False):
            return jsonify({
                "message": "Account blocked",
                "code": "ACCOUNT_BLOCKED",
                "block_reason": getattr(user, 'block_reason', '') or "Ваш аккаунт заблокирован",
                "blocked_at": user.blocked_at.isoformat() if hasattr(user, 'blocked_at') and user.blocked_at else None
            }), 403

        return jsonify({"token": create_local_jwt(user.id), "role": user.role}), 200
    except Exception as e:
        print(f"Login Error: {e}")
        return jsonify({"message": "Internal Server Error"}), 500


@app.route('/api/public/forgot-password', methods=['POST', 'OPTIONS'])
@limiter.limit("5 per hour")
def forgot_password():
    """Восстановление пароля"""
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response, 200

    try:
        data = request.json or {}
        email = data.get('email', '').strip().lower()

        if not email:
            return jsonify({"message": "Email is required"}), 400

        user = User.query.filter_by(email=email).first()
        if not user:
            from sqlalchemy import func
            user = User.query.filter(func.lower(User.email) == email).first()

        # Если не найден по email, пробуем найти по telegram_id (если передан)
        telegram_id = data.get('telegram_id')
        if not user and telegram_id:
            telegram_id_str = str(telegram_id)
            user = User.query.filter_by(telegram_id=telegram_id_str).first()

        if not user:
            return jsonify({"message": "If this email exists, a password reset link has been sent"}), 200

        # Генерируем новый пароль
        import secrets
        new_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
        
        hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        user.password_hash = hashed_password

        if fernet:
            try:
                user.encrypted_password = fernet.encrypt(new_password.encode()).decode()
            except:
                pass

        db.session.commit()

        # Отправка email
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>Восстановление пароля</h2>
            <p>Ваш новый пароль:</p>
            <div style="background: #f5f5f5; padding: 15px; font-family: monospace; font-size: 18px;">
                {new_password}
            </div>
            <p style="color: #666;">Рекомендуем изменить пароль после входа.</p>
        </body>
        </html>
        """

        threading.Thread(
            target=send_email_in_background,
            args=(app.app_context(), user.email, "Восстановление пароля", html_body),
            daemon=True
        ).start()

        return jsonify({"message": "If this email exists, a password reset link has been sent"}), 200

    except Exception as e:
        print(f"Forgot password error: {e}")
        return jsonify({"message": "If this email exists, a password reset link has been sent"}), 200


@app.route('/api/public/verify-email', methods=['POST'])
@limiter.limit("10 per minute")
def verify_email():
    """Подтверждение email"""
    try:
        token = request.json.get('token')
        if not isinstance(token, str):
            return jsonify({"message": "Invalid token"}), 400

        user = User.query.filter_by(verification_token=token).first()
        if not user:
            return jsonify({"message": "Invalid or expired token"}), 404

        user.is_verified = True
        user.verification_token = None
        db.session.commit()

        jwt_token = create_local_jwt(user.id)
        return jsonify({"message": "OK", "token": jwt_token, "role": user.role}), 200

    except Exception as e:
        return jsonify({"message": "Internal Error"}), 500


@app.route('/api/public/resend-verification', methods=['POST'])
@limiter.limit("3 per minute")
def resend_verification():
    """Повторная отправка подтверждения"""
    try:
        email = request.json.get('email')
        if not isinstance(email, str):
            return jsonify({"message": "Invalid email"}), 400

        user = User.query.filter_by(email=email).first()
        if user and not user.is_verified:
            if not user.verification_token:
                user.verification_token = ''.join(random.choices(string.ascii_letters + string.digits, k=50))
                db.session.commit()

            your_server_ip = os.getenv('YOUR_SERVER_IP') or os.getenv('YOUR_SERVER_IP_OR_DOMAIN')
            if your_server_ip:
                your_server_ip = your_server_ip.strip()
                if not your_server_ip.startswith(('http://', 'https://')):
                    your_server_ip = f"https://{your_server_ip}"
            else:
                your_server_ip = "https://testpanel.stealthnet.app"

            url = f"{your_server_ip}/verify?token={user.verification_token}"
            # Получаем branding и service_name для шаблона
            branding = BrandingSetting.query.first()
            bot_config = BotConfig.query.first()
            service_name = bot_config.service_name if bot_config else (branding.site_name if branding else "StealthNET")
            html = render_template('email_verification.html', 
                                 verification_url=url,
                                 branding=branding,
                                 service_name=service_name)
            threading.Thread(target=send_email_in_background, args=(app.app_context(), email, "Verify Email", html)).start()

        return jsonify({"message": "Sent"}), 200

    except Exception as e:
        return jsonify({"message": "Internal Error"}), 500


@app.route('/api/public/telegram-login', methods=['POST'])
@limiter.limit("10 per minute")
def telegram_login():
    """Авторизация через Telegram"""
    data = request.json or {}
    
    # Проверяем формат данных (может быть как объект с id, так и объект с telegram_id)
    telegram_id = data.get('id') or data.get('telegram_id')
    username = data.get('username', '')
    hash_value = data.get('hash')
    
    # Если telegram_id - строка, конвертируем в число
    if telegram_id and isinstance(telegram_id, str):
        try:
            telegram_id = int(telegram_id)
        except (ValueError, TypeError):
            pass

    if not telegram_id or not hash_value:
        print(f"Telegram login error: missing data. telegram_id={telegram_id}, hash={bool(hash_value)}, data_keys={list(data.keys()) if data else 'no data'}")
        return jsonify({"message": "Invalid Telegram data: missing id/telegram_id or hash"}), 400

    try:
        # Конвертируем telegram_id в строку для поиска в БД (в модели хранится как строка)
        telegram_id_str = str(telegram_id)
        user = User.query.filter_by(telegram_id=telegram_id_str).first()
        
        # Проверяем блокировку аккаунта
        if user and getattr(user, 'is_blocked', False):
            return jsonify({
                "message": "Account blocked",
                "code": "ACCOUNT_BLOCKED",
                "block_reason": getattr(user, 'block_reason', '') or "Ваш аккаунт заблокирован",
                "blocked_at": user.blocked_at.isoformat() if hasattr(user, 'blocked_at') and user.blocked_at else None
            }), 403

        if not user:
            BOT_API_URL = os.getenv("BOT_API_URL", "")
            BOT_API_TOKEN = os.getenv("BOT_API_TOKEN", "")

            if BOT_API_URL and BOT_API_TOKEN:
                try:
                    bot_api_url = BOT_API_URL.rstrip('/')
                    headers = {"X-API-Key": BOT_API_TOKEN}
                    
                    bot_resp = requests.get(f"{bot_api_url}/users/{telegram_id}", headers=headers, timeout=10)

                    if bot_resp.status_code == 200:
                        bot_data = bot_resp.json()
                        bot_user = bot_data.get('response', {}) if 'response' in bot_data else bot_data
                        remnawave_uuid = bot_user.get('remnawave_uuid') or bot_user.get('uuid')

                        if remnawave_uuid:
                            existing_user = User.query.filter_by(remnawave_uuid=remnawave_uuid).first()
                            if existing_user:
                                existing_user.telegram_id = telegram_id_str
                                existing_user.telegram_username = username
                                db.session.commit()
                                user = existing_user
                            else:
                                sys_settings = get_system_settings() or create_system_settings()
                                user = User(
                                    telegram_id=telegram_id_str,
                                    telegram_username=username,
                                    email=f"tg_{telegram_id}@telegram.local",
                                    password_hash='',
                                    remnawave_uuid=remnawave_uuid,
                                    is_verified=True,
                                    preferred_lang=sys_settings.default_language,
                                    preferred_currency=sys_settings.default_currency
                                )
                                db.session.add(user)
                                db.session.flush()
                                user.referral_code = generate_referral_code(user.id)
                                db.session.commit()
                        else:
                            return jsonify({"message": "User not found in bot"}), 404
                    else:
                        return jsonify({"message": "User not found"}), 404
                except Exception as e:
                    print(f"Bot API Error: {e}")
                    return jsonify({"message": "Bot API error"}), 500
            else:
                return jsonify({"message": "Bot API not configured"}), 500

        if username and user.telegram_username != username:
            user.telegram_username = username
            db.session.commit()

        cache.delete(f'live_data_{user.remnawave_uuid}')
        return jsonify({"token": create_local_jwt(user.id), "role": user.role}), 200

    except Exception as e:
        print(f"Telegram Login Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Internal Server Error"}), 500
