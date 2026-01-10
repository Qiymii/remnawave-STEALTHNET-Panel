"""
API эндпоинты для интеграции с Telegram ботом

- POST /api/bot/get-token - Получение JWT по Telegram ID
- POST /api/bot/register - Регистрация пользователя через бота
- POST /api/bot/get-credentials - Данные для подключения
"""

from flask import jsonify, request
import random
import string
import os

from modules.core import get_app, get_db
from modules.auth import create_local_jwt
from modules.models.user import User
from modules.models.system import SystemSetting
from modules.models.bot_config import BotConfig
from modules.models.referral import ReferralSetting

app = get_app()
db = get_db()


def generate_referral_code(user_id):
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
    return f"REF-{user_id}-{random_part}"


# ============================================================================
# BOT ENDPOINTS
# ============================================================================

@app.route('/api/bot/get-token', methods=['POST'])
def bot_get_token():
    """Получение JWT токена по Telegram ID или email/password"""
    try:
        data = request.json or {}
        telegram_id = data.get('telegram_id')
        email = data.get('email')
        password = data.get('password')

        user = None
        
        # Приоритет 1: Поиск по telegram_id
        if telegram_id:
            telegram_id_str = str(telegram_id)
            user = User.query.filter_by(telegram_id=telegram_id_str).first()
        
        # Приоритет 2: Если не найден по telegram_id, пробуем по email/password
        # (если пользователь зарегистрировался на сайте)
        if not user and email and password:
            user = User.query.filter_by(email=email).first()
            if user:
                # Проверяем пароль
                from modules.core import bcrypt
                if not user.password_hash or not bcrypt.check_password_hash(user.password_hash, password):
                    return jsonify({"message": "Invalid credentials"}), 401
                # Если пользователь найден по email/password, но у него нет telegram_id, связываем его
                if telegram_id and not user.telegram_id:
                    user.telegram_id = str(telegram_id)
                    db = get_db()
                    db.session.commit()
        
        if not user:
            return jsonify({"message": "User not found"}), 404
        
        # Проверяем блокировку аккаунта
        if getattr(user, 'is_blocked', False):
            return jsonify({
                "message": "Account blocked",
                "code": "ACCOUNT_BLOCKED",
                "block_reason": getattr(user, 'block_reason', '') or "Ваш аккаунт заблокирован",
                "blocked_at": user.blocked_at.isoformat() if hasattr(user, 'blocked_at') and user.blocked_at else None
            }), 403

        token = create_local_jwt(user.id)
        return jsonify({
            "token": token,
            "user_id": user.id,
            "role": user.role
        }), 200

    except Exception as e:
        print(f"Error in bot_get_token: {e}")
        return jsonify({"message": "Internal Server Error"}), 500


@app.route('/api/bot/register', methods=['POST'])
def bot_register():
    """Регистрация пользователя через бота (совместимо со старым API)"""
    try:
        data = request.json
        telegram_id = data.get('telegram_id')
        telegram_username = data.get('telegram_username', '')
        # Поддержка обоих вариантов для совместимости
        language_code = data.get('language_code') or data.get('preferred_lang', 'ru')
        referral_code = data.get('referral_code') or data.get('ref_code', '')
        preferred_currency = data.get('preferred_currency')

        if not telegram_id:
            return jsonify({"message": "telegram_id is required"}), 400

        # Проверяем существующего пользователя
        existing_user = User.query.filter_by(telegram_id=str(telegram_id)).first()
        if existing_user:
            return jsonify({
                "message": "User already registered",
                "user_id": existing_user.id,
                "token": create_local_jwt(existing_user.id)
            }), 200

        # Получаем системные настройки
        sys_settings = SystemSetting.query.first()
        if not sys_settings:
            sys_settings = SystemSetting(default_language='ru', default_currency='uah')
            db.session.add(sys_settings)
            db.session.flush()

        # Определяем валюту
        currency = preferred_currency or sys_settings.default_currency

        # Генерируем email и пароль
        import secrets
        email = f"tg_{telegram_id}@telegram.local"
        password = secrets.token_urlsafe(12)  # Генерируем случайный пароль
        
        # Обрабатываем реферальный код
        referrer = None
        if referral_code:
            referrer = User.query.filter_by(referral_code=referral_code).first()

        # Создаем пользователя в RemnaWave API (как в старом app.py)
        remnawave_uuid = None
        from modules.api.webhooks.routes import get_remnawave_headers
        from datetime import datetime, timedelta, timezone
        import requests
        
        API_URL = os.getenv('API_URL')
        ADMIN_TOKEN = os.getenv('ADMIN_TOKEN')
        DEFAULT_SQUAD_ID = os.getenv('DEFAULT_SQUAD_ID')
        
        if not API_URL or not ADMIN_TOKEN:
            return jsonify({"message": "RemnaWave API not configured (API_URL or ADMIN_TOKEN missing)"}), 500
        
        try:
            # Сначала проверяем, существует ли пользователь в RemnaWave по telegramId
            existing_remnawave_user = None
            if telegram_id:
                try:
                    telegram_id_int = int(telegram_id) if isinstance(telegram_id, (str, int)) else telegram_id
                    check_resp = requests.get(
                        f"{API_URL}/api/users/by-telegram-id/{telegram_id_int}",
                        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
                        timeout=15
                    )
                    if check_resp.status_code == 200:
                        check_data = check_resp.json()
                        # API может вернуть response с пользователем или массив пользователей
                        if check_data.get('response'):
                            existing_remnawave_user = check_data['response']
                            if isinstance(existing_remnawave_user, list) and len(existing_remnawave_user) > 0:
                                existing_remnawave_user = existing_remnawave_user[0]
                        print(f"Found existing user in RemnaWave by telegramId: {existing_remnawave_user.get('uuid') if existing_remnawave_user else 'None'}")
                except Exception as e:
                    print(f"Error checking existing user by telegramId: {e}")
            
            # Если пользователь уже существует в RemnaWave - используем его UUID
            if existing_remnawave_user and existing_remnawave_user.get('uuid'):
                remnawave_uuid = existing_remnawave_user.get('uuid')
                print(f"Using existing RemnaWave user UUID: {remnawave_uuid}")
            else:
                # Пользователь не найден - создаём нового
                # Бонусные дни для реферала
                bonus_days = 0
                if referrer:
                    ref_settings = ReferralSetting.query.first()
                    bonus_days = ref_settings.invitee_bonus_days if ref_settings else 7
                
                expire_date = (datetime.now(timezone.utc) + timedelta(days=bonus_days)).isoformat()
                clean_username = email.replace("@", "_").replace(".", "_")
                
                payload_create = {
                    "email": email,
                    "password": password,
                    "username": clean_username,
                    "expireAt": expire_date
                }
                
                # Добавляем activeInternalSquads только если есть реферал и DEFAULT_SQUAD_ID
                if referrer and DEFAULT_SQUAD_ID:
                    payload_create["activeInternalSquads"] = [DEFAULT_SQUAD_ID]
                
                # Добавляем telegramId только если он есть, и как число (не строку)
                if telegram_id:
                    try:
                        # Пробуем конвертировать в int, если это возможно
                        telegram_id_int = int(telegram_id) if isinstance(telegram_id, (str, int)) else telegram_id
                        payload_create["telegramId"] = telegram_id_int
                    except (ValueError, TypeError):
                        # Если не получается конвертировать, отправляем как строку
                        payload_create["telegramId"] = str(telegram_id)
                
                print(f"Creating user in RemnaWave with payload: {payload_create}")
                
                resp = requests.post(
                    f"{API_URL}/api/users",
                    headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
                    json=payload_create,
                    timeout=30
                )
                
                if resp.status_code != 200 and resp.status_code != 201:
                    error_text = resp.text[:500] if hasattr(resp, 'text') else 'No error details'
                    print(f"RemnaWave API Error: Status {resp.status_code}, Response: {error_text}")
                    try:
                        error_json = resp.json()
                        error_detail = error_json.get('message') or error_json.get('error') or error_text
                    except:
                        error_detail = error_text
                    raise requests.exceptions.HTTPError(f"{resp.status_code} Client Error: {error_detail} for url: {resp.url}", response=resp)
                
                resp.raise_for_status()
                remnawave_uuid = resp.json().get('response', {}).get('uuid')
                
                if not remnawave_uuid:
                    return jsonify({"message": "Provider Error: Failed to create user in RemnaWave (no UUID returned)"}), 500
                
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            # Обработка сетевых ошибок (DNS, таймауты, недоступность сервера)
            error_msg = str(e)
            print(f"Error creating user in RemnaWave (Network Error): {error_msg}")
            print(f"API_URL: {API_URL}")
            print(f"Payload was: {payload_create}")
            import traceback
            traceback.print_exc()
            return jsonify({
                "message": "Не удалось подключиться к RemnaWave API. Проверьте настройки API_URL и доступность сервера.",
                "error": error_msg,
                "api_url": API_URL
            }), 500
        except requests.exceptions.HTTPError as e:
            error_detail = ""
            try:
                if hasattr(e, 'response') and e.response:
                    error_response = e.response.json() if e.response else {}
                    error_detail = error_response.get('message') or error_response.get('error') or e.response.text[:200] or str(e)
                else:
                    error_detail = str(e)
            except:
                error_detail = str(e)
            print(f"Error creating user in RemnaWave: {error_detail}")
            print(f"Payload was: {payload_create}")
            return jsonify({
                "message": "Failed to create user in RemnaWave",
                "error": error_detail
            }), 500
        except Exception as e:
            print(f"Error creating user in RemnaWave: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({
                "message": "Failed to create user in RemnaWave",
                "error": str(e)
            }), 500

        # Создаем нового пользователя в локальной БД (только если remnawave_uuid получен)
        if not remnawave_uuid:
            return jsonify({"message": "Failed to get UUID from RemnaWave"}), 500
            
        # Хешируем пароль для возможности входа на сайте
        from modules.core import bcrypt, get_fernet
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        # Сохраняем зашифрованный пароль для старого бота (get-credentials)
        encrypted_password_str = None
        fernet = get_fernet()
        if fernet:
            try:
                encrypted_password_str = fernet.encrypt(password.encode()).decode()
            except Exception as e:
                print(f"Error encrypting password: {e}")
                encrypted_password_str = None
        
        new_user = User(
            telegram_id=str(telegram_id),  # Сохраняем как строку для совместимости
            telegram_username=telegram_username,
            email=email,
            password_hash=hashed_password,  # Сохраняем хеш пароля для входа на сайте
            encrypted_password=encrypted_password_str,  # Сохраняем зашифрованный пароль для старого бота
            remnawave_uuid=remnawave_uuid,  # Должен быть валидным UUID
            is_verified=True,
            preferred_lang=language_code,
            preferred_currency=currency
        )

        db.session.add(new_user)
        db.session.flush()

        new_user.referral_code = generate_referral_code(new_user.id)

        # Применяем реферальный код
        if referrer:
            new_user.referrer_id = referrer.id

        db.session.commit()

        token = create_local_jwt(new_user.id)

        # Отправляем уведомление админам о новом пользователе
        try:
            from modules.notifications import notify_new_user
            # Определяем источник регистрации (старый или новый бот)
            # По умолчанию используем старый бот, если не указано иное
            registration_source = "bot_old"
            notify_new_user(new_user, registration_source)
        except Exception as e:
            print(f"Error sending new user notification: {e}")

        # Возвращаем как в старом app.py (с email и password)
        response_data = {
            "message": "Registration successful",
            "email": email,
            "password": password,  # Возвращаем пароль только при регистрации
            "token": token,
            "user_id": new_user.id,
            "referral_code": new_user.referral_code
        }

        return jsonify(response_data), 201

    except Exception as e:
        db.session.rollback()
        print(f"Error in bot_register: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Internal Server Error"}), 500


@app.route('/api/bot/get-credentials', methods=['POST'])
def bot_get_credentials():
    """
    Получить логин (email) и пароль пользователя для входа на сайте.
    Пароль возвращается из зашифрованного хранилища, если доступен.
    Также возвращает данные для подключения (remnawave_uuid, server_domain).
    """
    try:
        data = request.json
        telegram_id = data.get('telegram_id')

        if not telegram_id:
            return jsonify({"message": "telegram_id is required"}), 400

        # Конвертируем в строку для поиска в БД (в модели хранится как строка)
        telegram_id_str = str(telegram_id)
        user = User.query.filter_by(telegram_id=telegram_id_str).first()
        if not user:
            return jsonify({"message": "User not found"}), 404

        if not user.email:
            return jsonify({"message": "User has no email/login"}), 404

        # Проверяем, есть ли пароль
        has_password = bool(user.password_hash and user.password_hash != '')
        
        # Пытаемся расшифровать пароль, если он сохранен
        password = None
        from modules.core import get_fernet
        fernet = get_fernet()
        if user.encrypted_password and fernet:
            try:
                password = fernet.decrypt(user.encrypted_password.encode()).decode()
            except Exception as e:
                print(f"Error decrypting password: {e}")
                password = None

        # Формируем ответ (совместимо со старым API)
        response = {
            "email": user.email,
            "has_password": has_password
        }
        
        if password:
            response["password"] = password
        elif not has_password:
            response["message"] = "No password set"
        else:
            response["message"] = "Password not available (contact support to reset)"
        
        # Добавляем данные для подключения (для совместимости)
        if user.remnawave_uuid:
            bot_config = BotConfig.query.first()
            response["remnawave_uuid"] = user.remnawave_uuid
            response["server_domain"] = os.getenv("YOUR_SERVER_IP") or os.getenv("YOUR_SERVER_IP_OR_DOMAIN", "testpanel.stealthnet.app")
            response["bot_config"] = {
                "service_name": bot_config.service_name if bot_config else "StealthNET",
                "support_url": bot_config.support_url if bot_config else "",
                "support_bot_username": bot_config.support_bot_username if bot_config else ""
            }

        return jsonify(response), 200

    except Exception as e:
        print(f"Error in bot_get_credentials: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Internal Server Error"}), 500
