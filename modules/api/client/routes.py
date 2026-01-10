"""
API эндпоинты клиента

- GET /api/client/me - Данные текущего пользователя
- POST /api/client/activate-trial - Активация триала
- POST /api/client/settings - Настройки пользователя
- POST /api/client/change-password - Смена пароля
- GET /api/client/nodes - Ноды пользователя
- POST /api/client/check-promocode - Проверка промокода
- POST /api/client/activate-promocode - Активация промокода
"""

from flask import request, jsonify
from datetime import datetime, timezone, timedelta
import requests
import json
import os
import time

from modules.core import get_app, get_db, get_cache, get_limiter, get_bcrypt
from modules.auth import get_user_from_token
from modules.models.user import User
from modules.models.promo import PromoCode
from modules.models.referral import ReferralSetting
from modules.currency import convert_from_usd, convert_to_usd, parse_iso_datetime, convert_to_usd, parse_iso_datetime
from modules.models.tariff import Tariff
from modules.models.payment import Payment, PaymentSetting
from modules.core import get_fernet
from modules.api.payments.base import decrypt_key, get_return_url

app = get_app()

# Глобальная сессия для Platega (сохранение cookies для обхода DDoS-Guard)
_platega_session = None
_platega_cookies_initialized = False

def _get_platega_session():
    """Получить или создать сессию для Platega"""
    global _platega_session, _platega_cookies_initialized
    if _platega_session is None:
        _platega_session = requests.Session()
        _platega_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })
    
    # Предварительный запрос для получения cookies от DDoS-Guard (только один раз)
    if not _platega_cookies_initialized:
        try:
            print("Platega: Initializing DDoS-Guard cookies...")
            _platega_session.get("https://app.platega.io/", timeout=10)
            _platega_cookies_initialized = True
            print("Platega: DDoS-Guard cookies initialized")
        except Exception as e:
            print(f"Platega: Warning - failed to initialize cookies: {e}")
    
    return _platega_session

def _reset_platega_cookies():
    """Сбросить cookies Platega и получить новые"""
    global _platega_cookies_initialized
    session = _get_platega_session()
    _platega_cookies_initialized = False
    session.cookies.clear()
    try:
        session.get("https://app.platega.io/", timeout=10)
        _platega_cookies_initialized = True
        print("Platega: New DDoS-Guard cookies obtained")
        return True
    except Exception as e:
        print(f"Platega: Failed to get new cookies: {e}")
        return False
db = get_db()
cache = get_cache()
limiter = get_limiter()


def get_remnawave_headers(additional_headers=None):
    """Получение заголовков для RemnaWave API"""
    headers = {}
    cookies = {}
    
    ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
    if ADMIN_TOKEN:
        headers["Authorization"] = f"Bearer {ADMIN_TOKEN}"
    
    REMNAWAVE_COOKIES_STR = os.getenv("REMNAWAVE_COOKIES", "")
    if REMNAWAVE_COOKIES_STR:
        try:
            cookies = json.loads(REMNAWAVE_COOKIES_STR)
        except json.JSONDecodeError:
            pass
    
    if additional_headers:
        headers.update(additional_headers)
    
    return headers, cookies


def get_referral_settings():
    return ReferralSetting.query.first()


# ============================================================================
# REFERRALS
# ============================================================================

@app.route('/api/client/referrals/info', methods=['GET'])
def get_client_referrals_info():
    """Получить информацию о реферальной программе для клиента"""
    user = get_user_from_token()
    if not user:
        return jsonify({"message": "Ошибка аутентификации"}), 401
    
    try:
        YOUR_SERVER_IP_OR_DOMAIN = os.getenv("YOUR_SERVER_IP_OR_DOMAIN", os.getenv("YOUR_SERVER_IP", ""))
        referral_code = user.referral_code or f"REF{user.id}"
        
        # Обновляем referral_code если его нет
        if not user.referral_code:
            user.referral_code = referral_code
            db.session.commit()
        
        referral_link_direct = f"{YOUR_SERVER_IP_OR_DOMAIN}/register?ref={referral_code}" if YOUR_SERVER_IP_OR_DOMAIN else ""
        # Используем функцию get_bot_username для единообразия
        # Приоритет: TELEGRAM_BOT_NAME_V2 -> TELEGRAM_BOT_NAME -> BOT_USERNAME -> CLIENT_BOT_USERNAME
        from modules.api.payments.base import get_bot_username
        bot_username = get_bot_username()
        if not bot_username:
            # Fallback если функция не вернула имя
            bot_username = os.getenv("TELEGRAM_BOT_NAME_V2") or os.getenv("TELEGRAM_BOT_NAME") or os.getenv("BOT_USERNAME") or os.getenv("CLIENT_BOT_USERNAME", "stealthnet_vpn_bot")
        referral_link_telegram = f"https://t.me/{bot_username}?start={referral_code}"
        
        # Получаем настройки реферальной программы
        ref_settings = get_referral_settings()
        referral_type = getattr(ref_settings, 'referral_type', 'DAYS') if ref_settings else 'DAYS'
        default_referral_percent = getattr(ref_settings, 'default_referral_percent', 10.0) if ref_settings else 10.0
        # Если у пользователя установлен индивидуальный процент - используем его, иначе глобальный
        user_referral_percent = user.referral_percent if user.referral_percent is not None else default_referral_percent
        
        # Информация в зависимости от типа системы
        referral_info = {}
        if referral_type == 'DAYS':
            invitee_days = ref_settings.invitee_bonus_days if ref_settings else 3
            referrer_days = ref_settings.referrer_bonus_days if ref_settings else 3
            referral_info = {
                "type": "DAYS",
                "title": "Реферальная программа на дни",
                "description": "Приглашайте друзей и получайте бесплатные дни подписки!",
                "invitee_bonus": f"{invitee_days} бесплатных дней",
                "referrer_bonus": f"{referrer_days} бесплатных дней за каждого приглашенного",
                "how_it_works": [
                    "Ваш друг регистрируется по вашей реферальной ссылке",
                    f"Он получает {invitee_days} бесплатных дней подписки",
                    f"Вы получаете {referrer_days} бесплатных дней за каждого приглашенного"
                ]
            }
        else:  # PERCENT
            referral_info = {
                "type": "PERCENT",
                "title": "Реферальная программа с процентами",
                "description": "Приглашайте друзей и получайте процент с их покупок на свой баланс!",
                "your_percent": f"{user_referral_percent}%",
                "default_percent": f"{default_referral_percent}%",
                "how_it_works": [
                    "Ваш друг регистрируется по вашей реферальной ссылке",
                    "Он покупает тариф или пополняет баланс",
                    f"Вы получаете {user_referral_percent}% от суммы на свой баланс",
                    "Средства можно использовать для покупки тарифов или вывести"
                ]
            }
        
        referrals_count = User.query.filter_by(referrer_id=user.id).count()
        
        return jsonify({
            "referral_code": referral_code,
            "referral_link_direct": referral_link_direct,
            "referral_link_telegram": referral_link_telegram,
            "referral_info": referral_info,
            "referrals_count": referrals_count
        }), 200
        
    except Exception as e:
        print(f"Error in get_client_referrals_info: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Internal Error"}), 500


# ============================================================================
# USER DATA
# ============================================================================

@app.route('/api/client/me', methods=['GET'])
def get_client_me():
    """Получение данных текущего пользователя"""
    user = get_user_from_token()
    if not user:
        return jsonify({"message": "Ошибка аутентификации"}), 401
    
    # Проверяем блокировку аккаунта
    if getattr(user, 'is_blocked', False):
        return jsonify({
            "message": "Account blocked",
            "code": "ACCOUNT_BLOCKED",
            "block_reason": getattr(user, 'block_reason', '') or "Ваш аккаунт заблокирован",
            "blocked_at": user.blocked_at.isoformat() if hasattr(user, 'blocked_at') and user.blocked_at else None
        }), 403

    current_uuid = user.remnawave_uuid
    
    # Проверка на короткий UUID
    is_short_uuid = (not current_uuid or '-' not in current_uuid or len(current_uuid) < 36)

    if is_short_uuid and current_uuid:
        # Попытка найти полный UUID
        if os.getenv("API_URL") and os.getenv("ADMIN_TOKEN"):
            try:
                resp = requests.get(
                    f"{os.getenv('API_URL')}/api/users/by-short-uuid/{current_uuid}",
                    headers={"Authorization": f"Bearer {os.getenv('ADMIN_TOKEN')}"},
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    user_data = data.get('response', {}) if isinstance(data, dict) and 'response' in data else data
                    found_uuid = user_data.get('uuid') if isinstance(user_data, dict) else None
                    
                    if found_uuid and '-' in found_uuid and len(found_uuid) >= 36:
                        old_uuid = user.remnawave_uuid
                        user.remnawave_uuid = found_uuid
                        db.session.commit()
                        current_uuid = found_uuid
                        if old_uuid:
                            cache.delete(f'live_data_{old_uuid}')
            except Exception as e:
                print(f"Error searching for user by shortUUID: {e}")

    cache_key = f'live_data_{current_uuid}'
    force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'

    if not force_refresh:
        cached = cache.get(cache_key)
        if cached:
            if isinstance(cached, dict):
                cached = cached.copy()
                balance_usd = float(user.balance) if user.balance else 0.0
                balance_converted = convert_from_usd(balance_usd, user.preferred_currency)
                cached.update({
                    'referral_code': user.referral_code,
                    'preferred_lang': user.preferred_lang,
                    'preferred_currency': user.preferred_currency,
                    'telegram_id': user.telegram_id,
                    'telegram_username': user.telegram_username,
                    'balance_usd': balance_usd,
                    'balance': balance_converted
                })
            return jsonify({"response": cached}), 200

    try:
        if is_short_uuid and current_uuid:
            return jsonify({
                "message": f"Некорректный UUID: {current_uuid}. Обратитесь к администратору.",
                "error": "INVALID_UUID_FORMAT"
            }), 400

        resp = requests.get(
            f"{os.getenv('API_URL')}/api/users/{current_uuid}",
            headers={"Authorization": f"Bearer {os.getenv('ADMIN_TOKEN')}"},
            timeout=10
        )

        if resp.status_code != 200:
            if resp.status_code == 404:
                # Если пользователь не найден в RemnaWave, проверяем кэш
                cached = cache.get(cache_key)
                if cached:
                    if isinstance(cached, dict):
                        cached = cached.copy()
                        balance_usd = float(user.balance) if user.balance else 0.0
                        cached.update({
                            'referral_code': user.referral_code,
                            'preferred_lang': user.preferred_lang,
                            'preferred_currency': user.preferred_currency,
                            'telegram_id': user.telegram_id,
                            'telegram_username': user.telegram_username,
                            'balance_usd': balance_usd,
                            'balance': convert_from_usd(balance_usd, user.preferred_currency)
                        })
                    return jsonify({"response": cached}), 200
                
                # Если кэша нет, возвращаем базовую информацию из нашей БД
                balance_usd = float(user.balance) if user.balance else 0.0
                balance_converted = convert_from_usd(balance_usd, user.preferred_currency)
                
                # Возвращаем минимальную информацию о пользователе
                basic_data = {
                    'uuid': current_uuid,
                    'email': user.email,
                    'referral_code': user.referral_code,
                    'preferred_lang': user.preferred_lang,
                    'preferred_currency': user.preferred_currency,
                    'telegram_id': user.telegram_id,
                    'telegram_username': user.telegram_username,
                    'password_hash': user.password_hash if user.password_hash else '',  # Добавляем password_hash
                    'balance_usd': balance_usd,
                    'balance': balance_converted,
                    'subscription': None,  # Нет подписки, т.к. пользователь не найден в RemnaWave
                    'warning': 'Пользователь не найден в RemnaWave API. Обратитесь к администратору.'
                }
                
                return jsonify({"response": basic_data}), 200
            return jsonify({"message": f"Ошибка RemnaWave: {resp.status_code}"}), 500

        response_data = resp.json()
        data = response_data.get('response', {}) if isinstance(response_data, dict) else response_data

        if isinstance(data, dict):
            balance_usd = float(user.balance) if user.balance else 0.0
            balance_converted = convert_from_usd(balance_usd, user.preferred_currency)
            data.update({
                'referral_code': user.referral_code,
                'preferred_lang': user.preferred_lang,
                'preferred_currency': user.preferred_currency,
                'telegram_id': user.telegram_id,
                'telegram_username': user.telegram_username,
                'password_hash': user.password_hash if user.password_hash else '',  # Добавляем password_hash
                'balance_usd': balance_usd,
                'balance': balance_converted
            })

        cache.set(cache_key, data, timeout=300)
        return jsonify({"response": data}), 200
        
    except requests.RequestException as e:
        cached = cache.get(cache_key)
        if cached:
            if isinstance(cached, dict):
                cached = cached.copy()
                balance_usd = float(user.balance) if user.balance else 0.0
                cached.update({
                    'referral_code': user.referral_code,
                    'preferred_lang': user.preferred_lang,
                    'preferred_currency': user.preferred_currency,
                    'telegram_id': user.telegram_id,
                    'telegram_username': user.telegram_username,
                    'password_hash': user.password_hash if user.password_hash else '',  # Добавляем password_hash
                    'balance_usd': balance_usd,
                    'balance': convert_from_usd(balance_usd, user.preferred_currency)
                })
            return jsonify({"response": cached}), 200
        return jsonify({"message": f"Ошибка подключения: {str(e)}"}), 500
    except Exception as e:
        print(f"Error in get_client_me: {e}")
        cached = cache.get(cache_key)
        if cached:
            return jsonify({"response": cached}), 200
        return jsonify({"message": "Internal Error"}), 500


@app.route('/api/client/activate-trial', methods=['POST'])
def activate_trial():
    """Активация триала"""
    user = get_user_from_token()
    if not user:
        return jsonify({"message": "Ошибка аутентификации"}), 401
    
    try:
        new_exp = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()

        referral_settings = get_referral_settings()
        trial_squad_id = os.getenv("DEFAULT_SQUAD_ID")
        if referral_settings and referral_settings.trial_squad_id:
            trial_squad_id = referral_settings.trial_squad_id

        headers, cookies = get_remnawave_headers()
        requests.patch(f"{os.getenv('API_URL')}/api/users", headers=headers, cookies=cookies,
                    json={"uuid": user.remnawave_uuid, "expireAt": new_exp, "activeInternalSquads": [trial_squad_id], "hwidDeviceLimit": 3})
        
        cache.delete(f'live_data_{user.remnawave_uuid}')
        cache.delete('all_live_users_map')
        cache.delete(f'nodes_{user.remnawave_uuid}')
        
        return jsonify({"message": "Trial activated"}), 200
    except Exception as e:
        return jsonify({"message": "Internal Error"}), 500


@app.route('/api/client/settings', methods=['POST'])
def set_settings():
    """Настройки клиента"""
    user = get_user_from_token()
    if not user:
        return jsonify({"message": "Ошибка аутентификации"}), 401

    try:
        data = request.json
        # Поддерживаем оба варианта: currency и preferred_currency для обратной совместимости
        if 'lang' in data:
            user.preferred_lang = data.get('lang')
        elif 'preferred_lang' in data:
            user.preferred_lang = data.get('preferred_lang')
        
        if 'currency' in data:
            currency = data.get('currency')
            if currency in ['uah', 'rub', 'usd']:
                user.preferred_currency = currency
        elif 'preferred_currency' in data:
            currency = data.get('preferred_currency')
            if currency in ['uah', 'rub', 'usd']:
                user.preferred_currency = currency
        
        db.session.commit()
        # Очищаем кэш пользователя при изменении настроек
        cache.delete(f'live_data_{user.remnawave_uuid}')
        cache.delete('all_live_users_map')
        return jsonify({"message": "Settings updated", "preferred_currency": user.preferred_currency}), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to update settings", "error": str(e)}), 500


@app.route('/api/client/link-telegram', methods=['POST'])
def link_telegram():
    """Связывание аккаунта с Telegram"""
    user = get_user_from_token()
    if not user:
        return jsonify({"message": "Ошибка аутентификации"}), 401

    try:
        data = request.json
        telegram_id = data.get('telegram_id')
        telegram_username = data.get('telegram_username', '')

        if not telegram_id:
            return jsonify({"message": "telegram_id is required"}), 400

        telegram_id_str = str(telegram_id)

        # Проверяем, не занят ли этот telegram_id другим пользователем
        existing_user = User.query.filter_by(telegram_id=telegram_id_str).first()
        if existing_user and existing_user.id != user.id:
            return jsonify({"message": "This Telegram account is already linked to another user"}), 400

        # Связываем аккаунт
        user.telegram_id = telegram_id_str
        if telegram_username:
            user.telegram_username = telegram_username
        db.session.commit()

        return jsonify({
            "message": "Telegram account linked successfully",
            "telegram_id": telegram_id_str
        }), 200
    except Exception as e:
        print(f"Error in link_telegram: {e}")
        return jsonify({"message": "Failed to link Telegram account"}), 500


@app.route('/api/client/change-password', methods=['POST'])
def change_password():
    """Изменение пароля"""
    user = get_user_from_token()
    if not user:
        return jsonify({"message": "Ошибка аутентификации"}), 401

    try:
        bcrypt = get_bcrypt()
        data = request.json
        current_password = data.get('current_password')
        new_password = data.get('new_password')

        if not new_password:
            return jsonify({"message": "New password is required"}), 400

        if len(new_password) < 6:
            return jsonify({"message": "Password must be at least 6 characters"}), 400

        # Если у пользователя нет пароля (зарегистрирован через бота), можно установить без текущего
        if not user.password_hash or user.password_hash == '':
            # Установка пароля для пользователя из бота (без проверки текущего)
            user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
            # Сохраняем зашифрованный пароль для бота
            fernet = get_fernet()
            if fernet:
                try:
                    user.encrypted_password = fernet.encrypt(new_password.encode()).decode()
                except:
                    pass
            db.session.commit()
            return jsonify({"message": "Password set successfully"}), 200

        # Если пароль уже есть, требуется текущий пароль
        if not current_password:
            return jsonify({"message": "Current password is required"}), 400

        if not bcrypt.check_password_hash(user.password_hash, current_password):
            return jsonify({"message": "Current password is incorrect"}), 401

        user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
        # Сохраняем зашифрованный пароль для бота
        fernet = get_fernet()
        if fernet:
            try:
                user.encrypted_password = fernet.encrypt(new_password.encode()).decode()
            except:
                pass
        db.session.commit()
        return jsonify({"message": "Password changed successfully"}), 200
    except Exception as e:
        print(f"Error in change_password: {e}")
        return jsonify({"message": "Failed to change password"}), 500


@app.route('/api/client/nodes', methods=['GET'])
def get_client_nodes():
    """Получение нод пользователя"""
    user = get_user_from_token()
    if not user:
        return jsonify({"message": "Ошибка аутентификации"}), 401
    
    # Проверяем параметр force_refresh для принудительного обновления
    force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
    
    if not force_refresh:
        cached = cache.get(f'nodes_{user.remnawave_uuid}')
        if cached:
            return jsonify(cached), 200
    
    try:
        headers, cookies = get_remnawave_headers()
        resp = requests.get(
            f"{os.getenv('API_URL')}/api/users/{user.remnawave_uuid}/accessible-nodes",
            headers=headers,
            cookies=cookies,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        cache.set(f'nodes_{user.remnawave_uuid}', data, timeout=600)
        return jsonify(data), 200
    except Exception as e:
        print(f"Error fetching nodes: {e}")
        return jsonify({"message": "Internal Error"}), 500


# ============================================================================
# PROMOCODES
# ============================================================================

@app.route('/api/client/check-promocode', methods=['POST'])
def check_promocode():
    """Проверка промокода"""
    user = get_user_from_token()
    if not user:
        return jsonify({"message": "Ошибка аутентификации"}), 401

    try:
        data = request.json or {}
        print(f"[PROMO] Request data: {data}")
        print(f"[PROMO] Request headers: {dict(request.headers)}")
        
        # Пробуем разные варианты ключей
        promo_code = (data.get('promo_code') or data.get('promoCode') or data.get('promo_code') or '').strip().upper()
        print(f"[PROMO] Extracted promo_code: '{promo_code}'")

        if not promo_code:
            print(f"[PROMO] ERROR: Promo code is empty or not provided")
            return jsonify({"message": "Promo code is required"}), 400

        promo = PromoCode.query.filter_by(code=promo_code).first()
        if not promo:
            return jsonify({"message": "Invalid promo code"}), 404

        if promo.uses_left <= 0:
            print(f"[PROMO] Promo code {promo_code} has no uses left: {promo.uses_left}")
            return jsonify({"message": "Promo code is no longer valid"}), 400

        # Логируем тип промокода для отладки
        print(f"[PROMO] Checking promo code: {promo_code}, type: {promo.promo_type}, uses_left: {promo.uses_left}")

        if promo.promo_type == 'PERCENT':
            return jsonify({
                "valid": True,
                "promo_type": "PERCENT",
                "value": promo.value,
                "description": f"{promo.value}% discount"
            }), 200
        elif promo.promo_type == 'FIXED':
            return jsonify({
                "valid": True,
                "promo_type": "FIXED",
                "value": promo.value,
                "description": f"{promo.value} fixed discount"
            }), 200
        elif promo.promo_type == 'DAYS':
            return jsonify({
                "valid": True,
                "promo_type": "DAYS",
                "value": promo.value,
                "description": f"{promo.value} free days"
            }), 200
        else:
            # Логируем неизвестный тип
            print(f"[PROMO] Unknown promo type: {promo.promo_type} for code: {promo_code}")
            return jsonify({
                "message": f"Unknown promo type: {promo.promo_type}",
                "promo_type": promo.promo_type
            }), 400

    except Exception as e:
        import traceback
        print(f"[PROMO] Error checking promo code: {e}")
        print(traceback.format_exc())
        return jsonify({"message": "Internal Error"}), 500


@app.route('/api/client/activate-promocode', methods=['POST'])
def activate_promocode():
    """Активация промокода"""
    user = get_user_from_token()
    if not user:
        return jsonify({"message": "Ошибка аутентификации"}), 401

    try:
        data = request.json
        promo_code = data.get('promo_code', '').strip().upper()
        
        print(f"[PROMO] Activate promocode request: code={promo_code}, user_id={user.id}")

        if not promo_code:
            print(f"[PROMO] Error: promo code is required")
            return jsonify({"message": "Promo code is required"}), 400

        promo = PromoCode.query.filter_by(code=promo_code).first()
        if not promo:
            print(f"[PROMO] Error: promo code '{promo_code}' not found")
            return jsonify({"message": "Invalid promo code"}), 404

        print(f"[PROMO] Found promo: type={promo.promo_type}, value={promo.value}, uses_left={promo.uses_left}")

        if promo.uses_left <= 0:
            print(f"[PROMO] Error: promo code '{promo_code}' has no uses left")
            return jsonify({"message": "Promo code is no longer valid"}), 400

        if promo.promo_type == 'DAYS':
            headers = {"Authorization": f"Bearer {os.getenv('ADMIN_TOKEN')}"}
            resp = requests.get(f"{os.getenv('API_URL')}/api/users/{user.remnawave_uuid}", headers=headers)

            if resp.status_code == 200:
                user_data = resp.json().get('response', {})
                current_expire = user_data.get('expireAt')

                if current_expire:
                    new_expire_dt = datetime.fromisoformat(current_expire) + timedelta(days=promo.value)
                else:
                    new_expire_dt = datetime.now(timezone.utc) + timedelta(days=promo.value)

                update_resp = requests.patch(
                    f"{os.getenv('API_URL')}/api/users",
                    headers=headers,
                    json={"uuid": user.remnawave_uuid, "expireAt": new_expire_dt.isoformat()}
                )

                if update_resp.status_code == 200:
                    promo.uses_left -= 1
                    db.session.commit()
                    cache.delete(f'live_data_{user.remnawave_uuid}')
                    return jsonify({
                        "message": f"Promo activated! +{promo.value} days",
                        "new_expire_date": new_expire_dt.isoformat()
                    }), 200
                print(f"[PROMO] Error: Failed to update subscription, resp={update_resp.status_code}")
                return jsonify({"message": "Failed to update subscription"}), 500
            print(f"[PROMO] Error: Failed to get user data, resp={resp.status_code}")
            return jsonify({"message": "Failed to get user data"}), 500
        else:
            print(f"[PROMO] Error: Promo code type '{promo.promo_type}' cannot be activated directly")
            return jsonify({"message": "This promo code type cannot be activated directly"}), 400

    except Exception as e:
        print(f"[PROMO] Exception: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Internal Error"}), 500


def decrypt_key(key):
    """Расшифровка ключа"""
    from modules.core import get_fernet
    fernet = get_fernet()
    if not key or not fernet:
        return ""
    try:
        return fernet.decrypt(key).decode('utf-8')
    except:
        return ""


# ============================================================================
# PURCHASE WITH BALANCE
# ============================================================================

@app.route('/api/client/purchase-with-balance', methods=['POST'])
@limiter.limit("10 per minute")
def purchase_with_balance():
    """Покупка тарифа с баланса пользователя"""
    user = get_user_from_token()
    if not user:
        return jsonify({"message": "Auth Error"}), 401
    
    try:
        data = request.json
        tariff_id = data.get('tariff_id')
        promo_code_str = data.get('promo_code', '').strip().upper() if data.get('promo_code') else None
        
        if not tariff_id:
            return jsonify({"message": "tariff_id is required"}), 400
        
        from modules.models.tariff import Tariff
        from modules.models.payment import Payment
        t = db.session.get(Tariff, tariff_id)
        if not t:
            return jsonify({"message": "Тариф не найден"}), 404
        
        # Определяем цену в валюте пользователя
        price_map = {"uah": {"a": t.price_uah, "c": "UAH"}, "rub": {"a": t.price_rub, "c": "RUB"}, "usd": {"a": t.price_usd, "c": "USD"}}
        info = price_map.get(user.preferred_currency, price_map['uah'])
        
        # Применяем промокод, если указан
        promo_code_obj = None
        final_amount = info['a']
        if promo_code_str:
            promo = PromoCode.query.filter_by(code=promo_code_str).first()
            if not promo:
                return jsonify({"message": "Неверный промокод"}), 400
            if promo.uses_left <= 0:
                return jsonify({"message": "Промокод больше не действителен"}), 400
            if promo.promo_type == 'PERCENT':
                discount = (promo.value / 100.0) * final_amount
                final_amount = final_amount - discount
                if final_amount < 0:
                    final_amount = 0
                promo_code_obj = promo
            elif promo.promo_type == 'FIXED':
                # Фиксированная скидка
                discount = float(promo.value)
                final_amount = final_amount - discount
                if final_amount < 0:
                    final_amount = 0
                promo_code_obj = promo
            elif promo.promo_type == 'DAYS':
                return jsonify({"message": "Промокод на бесплатные дни активируется отдельно"}), 400
        
        # Проверяем баланс пользователя
        current_balance_usd = float(user.balance) if user.balance else 0.0
        final_amount_usd = convert_to_usd(final_amount, info['c'])
        
        if current_balance_usd < final_amount_usd:
            current_balance_display = convert_from_usd(current_balance_usd, user.preferred_currency)
            return jsonify({
                "message": f"Недостаточно средств на балансе. Требуется: {final_amount:.2f} {info['c']}, доступно: {current_balance_display:.2f} {info['c']}"
            }), 400
        
        # Списываем средства с баланса
        user.balance = current_balance_usd - final_amount_usd
        
        # Активируем тариф
        API_URL = os.getenv('API_URL')
        DEFAULT_SQUAD_ID = os.getenv('DEFAULT_SQUAD_ID')
        h, c = get_remnawave_headers()
        live = requests.get(f"{API_URL}/api/users/{user.remnawave_uuid}", headers=h, cookies=c, timeout=10).json().get('response', {})
        curr_exp = parse_iso_datetime(live.get('expireAt'))
        if not curr_exp:
            curr_exp = datetime.now(timezone.utc)
        new_exp = max(datetime.now(timezone.utc), curr_exp) + timedelta(days=t.duration_days)
        
        # Получаем список сквадов из тарифа
        squad_ids = []
        if hasattr(t, 'get_squad_ids'):
            squad_ids = t.get_squad_ids()
        elif hasattr(t, 'squad_ids') and t.squad_ids:
            try:
                import json
                squad_ids = json.loads(t.squad_ids) if isinstance(t.squad_ids, str) else t.squad_ids
            except:
                squad_ids = []
        
        # Если сквады не указаны, используем дефолтный
        if not squad_ids:
            if t.squad_id:
                squad_ids = [t.squad_id]
            else:
                squad_ids = [DEFAULT_SQUAD_ID] if DEFAULT_SQUAD_ID else []
        
        patch_payload = {
            "uuid": user.remnawave_uuid,
            "expireAt": new_exp.isoformat(),
            "activeInternalSquads": squad_ids
        }
        
        if t.traffic_limit_bytes and t.traffic_limit_bytes > 0:
            patch_payload["trafficLimitBytes"] = t.traffic_limit_bytes
            patch_payload["trafficLimitStrategy"] = "NO_RESET"
        
        # Устанавливаем лимит устройств, если он указан в тарифе
        if hasattr(t, 'hwid_device_limit') and t.hwid_device_limit is not None and t.hwid_device_limit > 0:
            patch_payload["hwidDeviceLimit"] = t.hwid_device_limit
        
        h, c = get_remnawave_headers({"Content-Type": "application/json"})
        patch_resp = requests.patch(f"{API_URL}/api/users", headers=h, cookies=c, json=patch_payload, timeout=10)
        if not patch_resp.ok:
            user.balance = current_balance_usd
            db.session.rollback()
            return jsonify({"message": "Ошибка активации тарифа"}), 500
        
        # Списываем использование промокода
        if promo_code_obj:
            if promo_code_obj.uses_left > 0:
                promo_code_obj.uses_left -= 1
        
        # Создаем запись о платеже
        order_id = f"u{user.id}-t{t.id}-balance-{int(datetime.now().timestamp())}"
        new_p = Payment(
            order_id=order_id,
            user_id=user.id,
            tariff_id=t.id,
            status='PAID',
            amount=final_amount,
            currency=info['c'],
            payment_provider='balance',
            promo_code_id=promo_code_obj.id if promo_code_obj else None
        )
        db.session.add(new_p)
        db.session.commit()
        
        # Начисляем реферальную комиссию
        from modules.api.webhooks.routes import add_referral_commission
        add_referral_commission(user, final_amount_usd, is_tariff_purchase=True)
        db.session.commit()
        
        cache.delete(f'live_data_{user.remnawave_uuid}')
        cache.delete(f'nodes_{user.remnawave_uuid}')
        cache.delete('all_live_users_map')
        
        return jsonify({
            "message": "Тариф успешно активирован",
            "order_id": order_id,
            "new_expire_date": new_exp.isoformat()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Internal Error"}), 500


# ============================================================================
# CREATE PAYMENT
# ============================================================================

@app.route('/api/client/create-payment', methods=['POST'])
def create_payment():
    """Создание платежа (тариф или пополнение баланса)"""
    user = get_user_from_token()
    if not user:
        return jsonify({"message": "Auth Error"}), 401
    
    try:
        payment_type = request.json.get('type', 'tariff')
        tid = request.json.get('tariff_id')
        
        # Если это пополнение баланса
        if payment_type == 'balance_topup' or tid is None:
            amount = request.json.get('amount', 0)
            currency = request.json.get('currency', user.preferred_currency or 'uah')
            payment_provider = request.json.get('payment_provider', 'crystalpay')
            
            if not amount or amount <= 0:
                return jsonify({"message": "Неверная сумма"}), 400
            
            from modules.models.payment import PaymentSetting, Payment
            s = PaymentSetting.query.first()
            order_id = f"u{user.id}-balance-{int(datetime.now().timestamp())}"
            payment_url = None
            payment_system_id = None
            
            YOUR_SERVER_IP_OR_DOMAIN = os.getenv("YOUR_SERVER_IP", "https://panel.stealthnet.app")
            if not YOUR_SERVER_IP_OR_DOMAIN.startswith(('http://', 'https://')):
                YOUR_SERVER_IP_OR_DOMAIN = f"https://{YOUR_SERVER_IP_OR_DOMAIN}"
            
            currency_code_map = {"uah": "UAH", "rub": "RUB", "usd": "USD"}
            cp_currency = currency_code_map.get(currency.lower(), "UAH")
            
            if payment_provider == 'crystalpay':
                crystalpay_key = decrypt_key(s.crystalpay_api_key) if s else None
                crystalpay_secret = decrypt_key(s.crystalpay_api_secret) if s else None
                if not crystalpay_key or crystalpay_key == "DECRYPTION_ERROR" or not crystalpay_secret or crystalpay_secret == "DECRYPTION_ERROR":
                    return jsonify({"message": "CrystalPay не настроен"}), 500
                
                # Эндпоинт /api/client/create-payment используется только с сайта
                from modules.api.payments.base import get_return_url
                redirect_url = get_return_url(source='website')
                
                payload = {
                    "auth_login": crystalpay_key,
                    "auth_secret": crystalpay_secret,
                    "amount": f"{float(amount):.2f}",
                    "type": "purchase",
                    "currency": cp_currency,
                    "lifetime": 60,
                    "extra": order_id,
                    "callback_url": f"{YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/crystalpay",
                    "redirect_url": redirect_url
                }
                
                resp = requests.post("https://api.crystalpay.io/v3/invoice/create/", json=payload, timeout=10)
                if resp.ok:
                    data = resp.json()
                    if not data.get('errors'):
                        payment_url = data.get('url')
                        payment_system_id = data.get('id')
                    else:
                        print(f"CrystalPay Error for balance topup: {data.get('errors')}")
                else:
                    print(f"CrystalPay API Error: {resp.status_code} - {resp.text}")
            
            elif payment_provider == 'heleket':
                heleket_key = decrypt_key(s.heleket_api_key) if s else None
                if not heleket_key or heleket_key == "DECRYPTION_ERROR":
                    return jsonify({"message": "Heleket API key not configured"}), 500
                
                heleket_currency = cp_currency
                to_currency = None
                
                if cp_currency == 'USD':
                    heleket_currency = "USD"
                else:
                    heleket_currency = "USD"
                    to_currency = "USDT"
                
                # Эндпоинт /api/client/create-payment используется только с сайта
                from modules.api.payments.base import get_return_url
                redirect_url = get_return_url(source='website')
                
                payload = {
                    "amount": f"{float(amount):.2f}",
                    "currency": heleket_currency,
                    "order_id": order_id,
                    "url_return": redirect_url,
                    "url_callback": f"{YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/heleket"
                }
                
                if to_currency:
                    payload["to_currency"] = to_currency
                
                headers = {
                    "Authorization": f"Bearer {heleket_key}",
                    "Content-Type": "application/json"
                }
                
                resp = requests.post("https://api.heleket.com/v1/payment", json=payload, headers=headers, timeout=10)
                if resp.ok:
                    data = resp.json()
                    if data.get('state') == 0 and data.get('result'):
                        result = data.get('result', {})
                        payment_url = result.get('url')
                        payment_system_id = result.get('uuid')
                    else:
                        print(f"Heleket Error for balance topup: {data.get('message')}")
                else:
                    print(f"Heleket API Error: {resp.status_code} - {resp.text}")
            
            elif payment_provider == 'yookassa':
                if cp_currency != 'RUB':
                    return jsonify({"message": "YooKassa поддерживает только валюту RUB. Пожалуйста, выберите другую платежную систему или измените валюту на RUB."}), 400
                
                # Используем универсальную функцию создания платежа
                from modules.api.payments import create_payment as create_payment_provider
                
                payment_url, payment_system_id = create_payment_provider(
                    provider='yookassa',
                    amount=float(amount),
                    currency='RUB',
                    order_id=order_id,
                    user_email=user.email,
                    description=f"Пополнение баланса на сумму {float(amount):.2f} RUB",
                    source='website'  # Платеж с сайта, возврат на сайт
                )
                
                if not payment_url:
                    error_msg = payment_system_id or "Failed to create YooKassa payment"
                    print(f"YooKassa Error: {error_msg}")
                    return jsonify({"message": error_msg}), 500
            
            elif payment_provider == 'telegram_stars':
                bot_token = decrypt_key(s.telegram_bot_token) if s else None
                if not bot_token or bot_token == "DECRYPTION_ERROR":
                    return jsonify({"message": "Telegram Bot Token not configured"}), 500
                
                stars_amount = int(float(amount) * 100)
                if cp_currency == 'UAH':
                    stars_amount = int(float(amount) * 2.7)
                elif cp_currency == 'RUB':
                    stars_amount = int(float(amount) * 1.1)
                elif cp_currency == 'USD':
                    stars_amount = int(float(amount) * 100)
                
                if stars_amount < 1:
                    stars_amount = 1
                
                invoice_payload = {
                    "title": "Пополнение баланса StealthNET",
                    "description": f"Пополнение баланса на сумму {float(amount):.2f} {cp_currency}",
                    "payload": order_id,
                    "provider_token": "",
                    "currency": "XTR",
                    "prices": [
                        {
                            "label": f"Пополнение баланса {float(amount):.2f} {cp_currency}",
                            "amount": stars_amount
                        }
                    ]
                }
                
                resp = requests.post(
                    f"https://api.telegram.org/bot{bot_token}/createInvoiceLink",
                    json=invoice_payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10
                )
                if resp.ok:
                    data = resp.json()
                    if data.get('ok'):
                        payment_url = data.get('result')
                        payment_system_id = order_id
                    else:
                        print(f"Telegram Stars Error for balance topup: {data.get('description')}")
                else:
                    print(f"Telegram Stars API Error: {resp.status_code} - {resp.text}")
            
            elif payment_provider == 'freekassa':
                freekassa_shop_id = decrypt_key(s.freekassa_shop_id) if s else None
                freekassa_secret = decrypt_key(s.freekassa_secret) if s else None
                if not freekassa_shop_id or not freekassa_secret or freekassa_shop_id == "DECRYPTION_ERROR" or freekassa_secret == "DECRYPTION_ERROR":
                    return jsonify({"message": "Freekassa credentials not configured"}), 500
                
                import hashlib
                merchant_id = freekassa_shop_id
                secret = freekassa_secret
                freekassa_currency_map = {"RUB": "RUB", "USD": "USD", "EUR": "EUR", "UAH": "UAH", "KZT": "KZT"}
                freekassa_currency = freekassa_currency_map.get(cp_currency, "RUB")
                
                sign_str = f"{merchant_id}:{float(amount)}:{secret}:{order_id}"
                sign = hashlib.md5(sign_str.encode()).hexdigest()
                
                payment_url = f"https://pay.freekassa.ru/?m={merchant_id}&oa={float(amount)}&o={order_id}&s={sign}&currency={freekassa_currency}"
                payment_system_id = order_id
            
            elif payment_provider == 'robokassa':
                robokassa_login = decrypt_key(getattr(s, 'robokassa_merchant_login', None)) if s else None
                robokassa_password1 = decrypt_key(getattr(s, 'robokassa_password1', None)) if s else None
                if not robokassa_login or not robokassa_password1 or robokassa_login == "DECRYPTION_ERROR" or robokassa_password1 == "DECRYPTION_ERROR":
                    return jsonify({"message": "Robokassa credentials not configured"}), 500
                
                import hashlib
                signature_string = f"{robokassa_login}:{float(amount)}:{order_id}:{robokassa_password1}"
                signature = hashlib.md5(signature_string.encode('utf-8')).hexdigest()
                
                payment_url = f"https://auth.robokassa.ru/Merchant/Index.aspx?MerchantLogin={robokassa_login}&OutSum={float(amount)}&InvId={order_id}&SignatureValue={signature}&Description=Пополнение баланса&Culture=ru&IsTest=0"
                payment_system_id = order_id
            
            elif payment_provider == 'platega':
                import uuid
                import re
                platega_key = decrypt_key(getattr(s, 'platega_api_key', None)) if s else None
                platega_merchant_raw = decrypt_key(getattr(s, 'platega_merchant_id', None)) if s else None
                if not platega_key or not platega_merchant_raw or platega_key == "DECRYPTION_ERROR" or platega_merchant_raw == "DECRYPTION_ERROR":
                    print(f"Platega credentials error: key={bool(platega_key)}, merchant={bool(platega_merchant_raw)}")
                    return jsonify({"message": "Platega credentials not configured"}), 500
                
                if (not isinstance(platega_key, str) or not platega_key.strip() or 
                    not isinstance(platega_merchant_raw, str) or not platega_merchant_raw.strip()):
                    print("Platega credentials are empty or invalid after decryption")
                    return jsonify({"message": "Platega credentials are empty or invalid"}), 500
                
                # Обработка Merchant ID: согласно документации Platega, X-MerchantId должен быть UUID
                # Убираем префикс 'live_' если есть, и ищем UUID в строке
                platega_merchant = platega_merchant_raw.strip()
                
                # Если начинается с 'live_', убираем префикс
                if platega_merchant.startswith('live_'):
                    platega_merchant = platega_merchant[5:]
                
                # Пытаемся найти UUID в строке (формат: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
                uuid_pattern = r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
                uuid_match = re.search(uuid_pattern, platega_merchant)
                
                if uuid_match:
                    platega_merchant = uuid_match.group(0)
                    print(f"Platega: Извлечен UUID из Merchant ID: {platega_merchant}")
                else:
                    # Проверяем, является ли вся строка валидным UUID
                    try:
                        uuid.UUID(platega_merchant)
                        print(f"Platega: Merchant ID является валидным UUID: {platega_merchant}")
                    except ValueError:
                        print(f"Platega ERROR: Merchant ID не является UUID. Значение: '{platega_merchant_raw}' -> '{platega_merchant}'")
                        return jsonify({
                            "message": f"Platega Merchant ID должен быть в формате UUID. Текущее значение: '{platega_merchant_raw}'. Проверьте настройки платежной системы."
                        }), 500
                
                transaction_uuid = str(uuid.uuid4())
                
                payload = {
                    "paymentMethod": 2,
                    "paymentDetails": {
                        "amount": float(amount),
                        "currency": cp_currency
                    },
                    "description": f"Balance topup {order_id}",
                    "return": f"{YOUR_SERVER_IP_OR_DOMAIN}/miniapp/payment-success.html?order_id={order_id}",
                    "failedUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription",
                    "callbackUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/platega"
                }
                
                headers = {
                    "Content-Type": "application/json",
                    "X-MerchantId": platega_merchant,
                    "X-Secret": platega_key,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
                    "Origin": "https://app.platega.io",
                    "Referer": "https://app.platega.io/"
                }
                
                print(f"Platega balance topup request: merchant_id={platega_merchant[:10] if platega_merchant else 'N/A'}..., payload={payload}")
                print(f"Platega callbackUrl: {payload.get('callbackUrl', 'NOT SET')}")
                
                try:
                    session = _get_platega_session()
                    
                    # Пробуем сначала API endpoint (без DDoS-Guard), затем web endpoint
                    api_endpoints = [
                        "https://api.platega.io/transaction/process",
                        "https://app.platega.io/transaction/process"
                    ]
                    
                    resp = None
                    for endpoint in api_endpoints:
                        try:
                            print(f"Platega: Trying {endpoint}...")
                            if resp is not None:
                                time.sleep(1)
                            resp = session.post(endpoint, json=payload, headers=headers, timeout=30)
                            if resp.status_code == 200:
                                print(f"Platega: Success with {endpoint}")
                                break
                            elif resp.status_code != 403:
                                break
                        except Exception as e:
                            print(f"Platega: Error with {endpoint}: {e}")
                            continue
                    
                    if resp is None:
                        return jsonify({"message": "Platega API Error: Failed to connect"}), 500
                    
                    print(f"Platega response: status={resp.status_code}")
                    
                    # Если получили 403 от DDoS-Guard, сбрасываем cookies и пробуем снова
                    if resp.status_code == 403:
                        response_text = resp.text[:200] if resp.text else ""
                        if "DDoS-Guard" in response_text or "ddos-guard" in response_text.lower():
                            print("Platega: DDoS-Guard challenge detected, resetting session and retrying...")
                            if _reset_platega_cookies():
                                resp = session.post("https://app.platega.io/transaction/process", json=payload, headers=headers, timeout=30)
                                print(f"Platega retry response: status={resp.status_code}")
                    
                    # Обработка 401 Unauthorized
                    if resp.status_code == 401:
                        print(f"Platega 401 Error: Response text: {resp.text[:500] if resp.text else 'No response text'}")
                        print(f"Platega request headers: X-MerchantId={'present' if headers.get('X-MerchantId') else 'missing'}, X-Secret={'present' if headers.get('X-Secret') else 'missing'}")
                        print(f"Platega credentials: merchant_id length={len(platega_merchant) if platega_merchant else 0}, api_key length={len(platega_key) if platega_key else 0}")
                        try:
                            error_data = resp.json()
                            error_msg = error_data.get('message') or error_data.get('error') or 'Unauthorized'
                            print(f"Platega 401 Error: {error_data}")
                        except:
                            error_msg = resp.text[:200] if resp.text else 'Unauthorized'
                        return jsonify({
                            "message": f"Platega API Error: 401 Unauthorized. {error_msg}. Проверьте правильность API ключа и Merchant ID в настройках платежной системы."
                        }), 500
                    
                    if resp.status_code == 403:
                        response_text = resp.text[:500] if resp.text else ""
                        if "DDoS-Guard" in response_text or "ddos-guard" in response_text.lower():
                            error_msg = (
                                "Platega заблокировал запрос через DDoS-Guard. "
                                "Для решения проблемы необходимо добавить IP сервера в whitelist Platega. "
                                "Свяжитесь с поддержкой Platega и предоставьте IP: 192.3.209.113"
                            )
                        else:
                            try:
                                error_data = resp.json()
                                error_msg = error_data.get('message') or error_data.get('error') or 'Forbidden'
                                print(f"Platega 403 Error: {error_data}")
                            except:
                                error_msg = response_text or 'Forbidden'
                        return jsonify({"message": f"Platega API Error: {error_msg}"}), 500
                    
                    resp.raise_for_status()
                    payment_data = resp.json()
                    print(f"Platega response data: {payment_data}")
                    
                    # Согласно документации Platega: URL в поле "redirect", ID в "transactionId"
                    payment_url = payment_data.get('redirect') or payment_data.get('url') or payment_data.get('paymentUrl')
                    payment_system_id = payment_data.get('transactionId') or payment_data.get('id') or transaction_uuid
                    
                    if not payment_url:
                        print(f"Platega: No redirect URL in response: {payment_data}")
                        return jsonify({"message": "Не удалось получить ссылку на оплату от Platega"}), 500
                        
                except requests.exceptions.HTTPError as e:
                    print(f"Platega HTTP Error: {e}")
                    return jsonify({"message": f"Platega API Error: {str(e)}"}), 500
                except Exception as e:
                    print(f"Platega Error: {e}")
                    return jsonify({"message": f"Platega Error: {str(e)}"}), 500
            
            else:
                return jsonify({"message": f"Неподдерживаемый способ оплаты: {payment_provider}"}), 400
            
            if not payment_url:
                return jsonify({"message": "Не удалось создать платеж"}), 500
            
            # Создаем запись о платеже
            new_p = Payment(
                order_id=order_id,
                user_id=user.id,
                tariff_id=None,
                status='PENDING',
                amount=float(amount),
                currency=currency_code_map.get(currency.lower(), "UAH"),
                payment_system_id=str(payment_system_id) if payment_system_id else order_id,
                payment_provider=payment_provider
            )
            db.session.add(new_p)
            try:
                db.session.commit()
            except Exception as e:
                print(f"Error creating payment record: {e}")
                db.session.rollback()
                return jsonify({"message": "Ошибка создания платежа"}), 500
            
            return jsonify({"payment_url": payment_url, "order_id": order_id}), 200
        
        # Покупка тарифа
        else:
            # Проверяем тип
            if not isinstance(tid, int):
                return jsonify({"message": "Invalid ID"}), 400
            
            promo_code_str = request.json.get('promo_code', '').strip().upper() if request.json.get('promo_code') else None
            payment_provider = request.json.get('payment_provider', 'crystalpay')
            
            from modules.models.tariff import Tariff
            t = db.session.get(Tariff, tid)
            if not t:
                return jsonify({"message": "Not found"}), 404
            
            price_map = {"uah": {"a": t.price_uah, "c": "UAH"}, "rub": {"a": t.price_rub, "c": "RUB"}, "usd": {"a": t.price_usd, "c": "USD"}}
            info = price_map.get(user.preferred_currency, price_map['uah'])
            
            # Применяем промокод со скидкой, если указан
            promo_code_obj = None
            final_amount = info['a']
            if promo_code_str:
                promo = PromoCode.query.filter_by(code=promo_code_str).first()
                if not promo:
                    return jsonify({"message": "Неверный промокод"}), 400
                if promo.uses_left <= 0:
                    return jsonify({"message": "Промокод больше не действителен"}), 400
                if promo.promo_type == 'PERCENT':
                    discount = (promo.value / 100.0) * final_amount
                    final_amount = final_amount - discount
                    if final_amount < 0:
                        final_amount = 0
                    promo_code_obj = promo
                elif promo.promo_type == 'FIXED':
                    # Фиксированная скидка
                    discount = float(promo.value)
                    final_amount = final_amount - discount
                    if final_amount < 0:
                        final_amount = 0
                    promo_code_obj = promo
                elif promo.promo_type == 'DAYS':
                    return jsonify({"message": "Промокод на бесплатные дни активируется отдельно"}), 400
            
            from modules.models.payment import PaymentSetting, Payment
            s = PaymentSetting.query.first()
            order_id = f"u{user.id}-t{t.id}-{int(datetime.now().timestamp())}"
            payment_url = None
            payment_system_id = None
            
            YOUR_SERVER_IP_OR_DOMAIN = os.getenv("YOUR_SERVER_IP", "https://panel.stealthnet.app")
            if not YOUR_SERVER_IP_OR_DOMAIN.startswith(('http://', 'https://')):
                YOUR_SERVER_IP_OR_DOMAIN = f"https://{YOUR_SERVER_IP_OR_DOMAIN}"
            
            # CrystalPay
            if payment_provider == 'crystalpay':
                crystalpay_key = decrypt_key(s.crystalpay_api_key) if s else None
                crystalpay_secret = decrypt_key(s.crystalpay_api_secret) if s else None
                if not crystalpay_key or crystalpay_key == "DECRYPTION_ERROR" or not crystalpay_secret or crystalpay_secret == "DECRYPTION_ERROR":
                    return jsonify({"message": "CrystalPay не настроен"}), 500
                
                # Эндпоинт /api/client/create-payment используется только с сайта
                from modules.api.payments.base import get_return_url
                redirect_url = get_return_url(source='website')
                
                payload = {
                    "auth_login": crystalpay_key,
                    "auth_secret": crystalpay_secret,
                    "amount": f"{final_amount:.2f}",
                    "type": "purchase",
                    "currency": info['c'],
                    "lifetime": 60,
                    "extra": order_id,
                    "callback_url": f"{YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/crystalpay",
                    "redirect_url": redirect_url
                }
                
                resp = requests.post("https://api.crystalpay.io/v3/invoice/create/", json=payload, timeout=10)
                if resp.ok:
                    data = resp.json()
                    if not data.get('errors'):
                        payment_url = data.get('url')
                        payment_system_id = data.get('id')
                    else:
                        print(f"CrystalPay Error: {data.get('errors')}")
                else:
                    print(f"CrystalPay API Error: {resp.status_code} - {resp.text}")
            
            # Heleket
            elif payment_provider == 'heleket':
                heleket_key = decrypt_key(s.heleket_api_key) if s else None
                if not heleket_key or heleket_key == "DECRYPTION_ERROR":
                    return jsonify({"message": "Heleket API key not configured"}), 500
                
                heleket_currency = info['c']
                to_currency = None
                
                if info['c'] == 'USD':
                    heleket_currency = "USD"
                else:
                    heleket_currency = "USD"
                    to_currency = "USDT"
                
                payload = {
                    "amount": f"{final_amount:.2f}",
                    "currency": heleket_currency,
                    "order_id": order_id,
                    "url_return": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription",
                    "url_callback": f"{YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/heleket"
                }
                
                if to_currency:
                    payload["to_currency"] = to_currency
                
                headers = {
                    "Authorization": f"Bearer {heleket_key}",
                    "Content-Type": "application/json"
                }
                
                resp = requests.post("https://api.heleket.com/v1/payment", json=payload, headers=headers, timeout=10)
                resp_data = resp.json()
                if resp_data.get('state') != 0 or not resp_data.get('result'):
                    error_msg = resp_data.get('message', 'Payment Provider Error')
                    print(f"Heleket Error: {error_msg}")
                    return jsonify({"message": error_msg}), 500
                
                result = resp_data.get('result', {})
                payment_url = result.get('url')
                payment_system_id = result.get('uuid')
            
            # YooKassa
            elif payment_provider == 'yookassa':
                if info['c'] != 'RUB':
                    return jsonify({"message": "YooKassa supports only RUB currency"}), 400
                
                # Используем универсальную функцию создания платежа
                from modules.api.payments import create_payment as create_payment_provider
                
                payment_url, payment_system_id = create_payment_provider(
                    provider='yookassa',
                    amount=final_amount,
                    currency='RUB',
                    order_id=order_id,
                    user_email=user.email,
                    description=f"Подписка StealthNET - {t.name} ({t.duration_days} дней)",
                    source='website'  # Платеж с сайта, возврат на сайт
                )
                
                if not payment_url:
                    error_msg = payment_system_id or "Failed to create YooKassa payment"
                    return jsonify({"message": error_msg}), 500
            
            # Telegram Stars
            elif payment_provider == 'telegram_stars':
                bot_token = decrypt_key(s.telegram_bot_token) if s else None
                if not bot_token or bot_token == "DECRYPTION_ERROR":
                    return jsonify({"message": "Telegram Bot Token not configured"}), 500
                
                stars_amount = int(final_amount * 100)
                if info['c'] == 'UAH':
                    stars_amount = int(final_amount * 2.7)
                elif info['c'] == 'RUB':
                    stars_amount = int(final_amount * 1.1)
                elif info['c'] == 'USD':
                    stars_amount = int(final_amount * 100)
                
                if stars_amount < 1:
                    stars_amount = 1
                
                invoice_payload = {
                    "title": f"Подписка StealthNET - {t.name}",
                    "description": f"Подписка на {t.duration_days} дней",
                    "payload": order_id,
                    "provider_token": "",
                    "currency": "XTR",
                    "prices": [
                        {
                            "label": f"Подписка {t.duration_days} дней",
                            "amount": stars_amount
                        }
                    ]
                }
                
                resp = requests.post(
                    f"https://api.telegram.org/bot{bot_token}/createInvoiceLink",
                    json=invoice_payload,
                    headers={"Content-Type": "application/json"}
                ).json()
                
                if not resp.get('ok'):
                    error_msg = resp.get('description', 'Telegram Bot API Error')
                    print(f"Telegram Stars Error: {error_msg}")
                    return jsonify({"message": error_msg}), 500
                
                payment_url = resp.get('result')
                payment_system_id = order_id
            
            # FreeKassa
            elif payment_provider == 'freekassa':
                freekassa_shop_id = decrypt_key(s.freekassa_shop_id) if s else None
                freekassa_secret = decrypt_key(s.freekassa_secret) if s else None
                if not freekassa_shop_id or not freekassa_secret or freekassa_shop_id == "DECRYPTION_ERROR" or freekassa_secret == "DECRYPTION_ERROR":
                    return jsonify({"message": "FreeKassa credentials not configured"}), 500
                
                import hashlib
                merchant_id = freekassa_shop_id
                secret = freekassa_secret
                amount = final_amount
                currency_map = {'RUB': 'RUB', 'UAH': 'UAH', 'USD': 'USD'}
                currency = currency_map.get(info['c'], 'RUB')
                
                # Формируем подпись
                sign_str = f"{merchant_id}:{amount}:{secret}:{order_id}"
                sign = hashlib.md5(sign_str.encode()).hexdigest()
                
                payment_url = f"https://pay.freekassa.ru/?m={merchant_id}&oa={amount}&o={order_id}&s={sign}&currency={currency}"
                payment_system_id = order_id
            
            # Robokassa
            elif payment_provider == 'robokassa':
                robokassa_login = decrypt_key(getattr(s, 'robokassa_merchant_login', None)) if s else None
                robokassa_password1 = decrypt_key(getattr(s, 'robokassa_password1', None)) if s else None
                if not robokassa_login or not robokassa_password1 or robokassa_login == "DECRYPTION_ERROR" or robokassa_password1 == "DECRYPTION_ERROR":
                    return jsonify({"message": "Robokassa credentials not configured"}), 500
                
                import hashlib
                merchant_login = robokassa_login
                password1 = robokassa_password1
                amount = final_amount
                currency_map = {'RUB': 'RUB', 'UAH': 'UAH', 'USD': 'USD'}
                currency = currency_map.get(info['c'], 'RUB')
                
                # Формируем подпись
                sign_str = f"{merchant_login}:{amount}:{order_id}:{password1}"
                sign = hashlib.md5(sign_str.encode()).hexdigest()
                
                payment_url = f"https://auth.robokassa.ru/Merchant/Index.aspx?MerchantLogin={merchant_login}&OutSum={amount}&InvId={order_id}&SignatureValue={sign}&Culture=ru&Currency={currency}"
                payment_system_id = order_id
            
            # CryptoBot
            elif payment_provider == 'cryptobot':
                cryptobot_key = decrypt_key(s.cryptobot_api_key) if s else None
                if not cryptobot_key or cryptobot_key == "DECRYPTION_ERROR":
                    return jsonify({"message": "CryptoBot API key not configured"}), 500
                
                payload = {
                    "amount": final_amount,
                    "currency_code": info['c'],
                    "description": f"Подписка StealthNET - {t.name}",
                    "paid_btn_name": "callback",
                    "paid_btn_url": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription"
                }
                
                headers = {
                    "Crypto-Pay-API-Token": cryptobot_key,
                    "Content-Type": "application/json"
                }
                
                resp = requests.post("https://pay.crypt.bot/api/createInvoice", json=payload, headers=headers, timeout=10)
                if resp.ok:
                    data = resp.json()
                    if data.get('ok'):
                        result = data.get('result', {})
                        payment_url = result.get('pay_url')
                        payment_system_id = str(result.get('invoice_id'))
                    else:
                        print(f"CryptoBot Error: {data.get('error')}")
                else:
                    print(f"CryptoBot API Error: {resp.status_code} - {resp.text}")
            
            # Monobank
            elif payment_provider == 'monobank':
                monobank_token = decrypt_key(getattr(s, 'monobank_token', None)) if s else None
                if not monobank_token or monobank_token == "DECRYPTION_ERROR":
                    return jsonify({"message": "Monobank token not configured"}), 500
                
                amount_in_kopecks = int(final_amount * 100)
                currency_code = 980  # UAH
                if info['c'] == 'RUB':
                    currency_code = 643
                elif info['c'] == 'USD':
                    currency_code = 840
                
                payload = {
                    "amount": amount_in_kopecks,
                    "ccy": currency_code,
                    "merchantPaymInfo": {
                        "reference": order_id,
                        "destination": f"Подписка StealthNET - {t.name}",
                        "comment": f"Подписка на {t.duration_days} дней"
                    },
                    "redirectUrl": get_return_url(source='website'),
                    "webHookUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/monobank",
                    "validity": 3600,
                    "paymentType": "debit"
                }
                
                headers = {
                    "X-Token": monobank_token,
                    "Content-Type": "application/json"
                }
                
                resp = requests.post("https://api.monobank.ua/api/merchant/invoice/create", json=payload, headers=headers, timeout=30)
                if resp.ok:
                    data = resp.json()
                    payment_url = data.get('pageUrl')
                    payment_system_id = data.get('invoiceId')
                else:
                    print(f"Monobank API Error: {resp.status_code} - {resp.text}")
            
            # Platega
            elif payment_provider == 'platega':
                import uuid
                import re
                platega_key = decrypt_key(getattr(s, 'platega_api_key', None)) if s else None
                platega_merchant_raw = decrypt_key(getattr(s, 'platega_merchant_id', None)) if s else None
                if not platega_key or not platega_merchant_raw or platega_key == "DECRYPTION_ERROR" or platega_merchant_raw == "DECRYPTION_ERROR":
                    print(f"Platega credentials error: key={bool(platega_key)}, merchant={bool(platega_merchant_raw)}")
                    return jsonify({"message": "Platega credentials not configured"}), 500
                
                # Проверяем, что ключи не пустые после расшифровки
                if (not isinstance(platega_key, str) or not platega_key.strip() or 
                    not isinstance(platega_merchant_raw, str) or not platega_merchant_raw.strip()):
                    print("Platega credentials are empty or invalid after decryption")
                    return jsonify({"message": "Platega credentials are empty or invalid"}), 500
                
                # Обработка Merchant ID: согласно документации Platega, X-MerchantId должен быть UUID
                # Убираем префикс 'live_' если есть, и ищем UUID в строке
                platega_merchant = platega_merchant_raw.strip()
                
                # Если начинается с 'live_', убираем префикс
                if platega_merchant.startswith('live_'):
                    platega_merchant = platega_merchant[5:]
                
                # Пытаемся найти UUID в строке (формат: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
                uuid_pattern = r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
                uuid_match = re.search(uuid_pattern, platega_merchant)
                
                if uuid_match:
                    platega_merchant = uuid_match.group(0)
                    print(f"Platega: Извлечен UUID из Merchant ID: {platega_merchant}")
                else:
                    # Проверяем, является ли вся строка валидным UUID
                    try:
                        uuid.UUID(platega_merchant)
                        print(f"Platega: Merchant ID является валидным UUID: {platega_merchant}")
                    except ValueError:
                        print(f"Platega ERROR: Merchant ID не является UUID. Значение: '{platega_merchant_raw}' -> '{platega_merchant}'")
                        return jsonify({
                            "message": f"Platega Merchant ID должен быть в формате UUID. Текущее значение: '{platega_merchant_raw}'. Проверьте настройки платежной системы."
                        }), 500
                
                transaction_uuid = str(uuid.uuid4())
                
                # Согласно документации Platega: ID транзакции генерируется системой автоматически
                # НЕ передаем поле "id" в запросе
                payload = {
                    "paymentMethod": 2,
                    "paymentDetails": {
                        "amount": float(final_amount),  # Должно быть float, не int
                        "currency": info['c']
                    },
                    "description": f"Payment for order {transaction_uuid}",
                    "return": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription",
                    "failedUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription",
                    "callbackUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/platega"
                }
                
                headers = {
                    "Content-Type": "application/json",
                    "X-MerchantId": platega_merchant,
                    "X-Secret": platega_key,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
                    "Origin": "https://app.platega.io",
                    "Referer": "https://app.platega.io/"
                }

                # Логируем для диагностики (без полных ключей)
                print(f"Platega request: merchant_id={platega_merchant[:10] if platega_merchant else 'N/A'}... (len={len(platega_merchant) if platega_merchant else 0}), key_len={len(platega_key) if platega_key else 0}, payload={payload}")
                print(f"Platega headers: X-MerchantId present={bool(platega_merchant)}, X-Secret present={bool(platega_key)}")
                
                try:
                    session = _get_platega_session()
                    
                    # Пробуем сначала API endpoint (без DDoS-Guard), затем web endpoint
                    api_endpoints = [
                        "https://api.platega.io/transaction/process",
                        "https://app.platega.io/transaction/process"
                    ]
                    
                    resp = None
                    for endpoint in api_endpoints:
                        try:
                            print(f"Platega: Trying {endpoint}...")
                            if resp is not None:
                                time.sleep(1)
                            resp = session.post(endpoint, json=payload, headers=headers, timeout=30)
                            if resp.status_code == 200:
                                print(f"Platega: Success with {endpoint}")
                                break
                            elif resp.status_code != 403:
                                break
                        except Exception as e:
                            print(f"Platega: Error with {endpoint}: {e}")
                            continue
                    
                    if resp is None:
                        return jsonify({"message": "Platega API Error: Failed to connect"}), 500
                    
                    # Логируем детали ответа для диагностики
                    print(f"Platega response: status={resp.status_code}, headers={dict(resp.headers)}")
                    if resp.status_code != 200:
                        print(f"Platega error response: {resp.text[:500]}")
                    
                    # Если получили 401, проверяем заголовки
                    # Обработка 401 Unauthorized
                    if resp.status_code == 401:
                        print(f"Platega 401 Error: Response text: {resp.text[:500] if resp.text else 'No response text'}")
                        print(f"Platega request headers: X-MerchantId={'present' if headers.get('X-MerchantId') else 'missing'}, X-Secret={'present' if headers.get('X-Secret') else 'missing'}")
                        print(f"Platega credentials: merchant_id length={len(platega_merchant) if platega_merchant else 0}, api_key length={len(platega_key) if platega_key else 0}")
                        try:
                            error_data = resp.json()
                            error_msg = error_data.get('message') or error_data.get('error') or 'Unauthorized'
                            print(f"Platega 401 Error: {error_data}")
                        except:
                            error_msg = resp.text[:200] if resp.text else 'Unauthorized'
                        return jsonify({
                            "message": f"Platega API Error: 401 Unauthorized. {error_msg}. Проверьте правильность API ключа и Merchant ID в настройках платежной системы."
                        }), 500
                    
                    # Если получили 403 от DDoS-Guard, сбрасываем cookies и пробуем снова
                    if resp.status_code == 403:
                        response_text = resp.text[:200] if resp.text else ""
                        if "DDoS-Guard" in response_text or "ddos-guard" in response_text.lower():
                            print("Platega: DDoS-Guard challenge detected, resetting session and retrying...")
                            if _reset_platega_cookies():
                                resp = session.post("https://app.platega.io/transaction/process", json=payload, headers=headers, timeout=30)
                                print(f"Platega retry response: status={resp.status_code}")
                        
                        # Проверяем 401 после retry
                        if resp.status_code == 401:
                            print(f"Platega 401 Error after retry: Response text: {resp.text[:500] if resp.text else 'No response text'}")
                            try:
                                error_data = resp.json()
                                error_msg = error_data.get('message') or error_data.get('error') or 'Unauthorized'
                            except:
                                error_msg = resp.text[:200] if resp.text else 'Unauthorized'
                            return jsonify({
                                "message": f"Platega API Error: 401 Unauthorized. {error_msg}. Проверьте правильность API ключа и Merchant ID в настройках платежной системы."
                            }), 500
                        
                        # Если все еще 403, возвращаем ошибку
                        if resp.status_code == 403:
                            response_text_full = resp.text[:500] if resp.text else ""
                            if "DDoS-Guard" in response_text_full or "ddos-guard" in response_text_full.lower():
                                error_msg = (
                                    "Platega заблокировал запрос через DDoS-Guard. "
                                    "Для решения проблемы необходимо добавить IP сервера в whitelist Platega. "
                                    "Свяжитесь с поддержкой Platega и предоставьте IP: 192.3.209.113"
                                )
                            else:
                                try:
                                    error_data = resp.json()
                                    error_msg = error_data.get('message') or error_data.get('error') or error_data.get('detail') or 'Forbidden'
                                    print(f"Platega 403 Error details: {error_data}")
                                except:
                                    error_msg = response_text_full or 'Forbidden - Invalid credentials or insufficient permissions'
                                    print(f"Platega 403 Error (non-JSON): {error_msg}")
                            
                            return jsonify({
                                "message": f"Platega API Error: {error_msg}. Проверьте правильность API ключа и Merchant ID в настройках платежей."
                            }), 500
                    
                    resp.raise_for_status()
                    payment_data = resp.json()
                    
                    payment_url = payment_data.get('redirect')
                    payment_system_id = payment_data.get('transactionId') or transaction_uuid
                    
                    if not payment_url:
                        error_msg = payment_data.get('message', 'Failed to get payment URL from Platega')
                        print(f"Platega Error: {error_msg}, response: {payment_data}")
                        return jsonify({"message": error_msg}), 500
                except requests.exceptions.HTTPError as e:
                    # Обработка HTTP ошибок (4xx, 5xx)
                    error_msg = str(e)
                    error_detail = ""
                    if hasattr(e, 'response') and e.response is not None:
                        try:
                            error_data = e.response.json()
                            error_detail = error_data.get('message') or error_data.get('error') or error_data.get('detail') or str(e)
                            print(f"Platega HTTP Error {e.response.status_code}: {error_data}")
                        except:
                            error_detail = e.response.text[:500] if e.response.text else str(e)
                            print(f"Platega HTTP Error {e.response.status_code} (non-JSON): {error_detail}")
                    else:
                        error_detail = error_msg
                    
                    return jsonify({
                        "message": f"Platega API Error: {error_detail}"
                    }), 500
                except requests.exceptions.RequestException as e:
                    # Обработка сетевых ошибок
                    error_msg = str(e)
                    print(f"Platega Request Error: {error_msg}")
                    return jsonify({
                        "message": f"Platega API Error: {error_msg}"
                    }), 500
            
            # Mulenpay
            elif payment_provider == 'mulenpay':
                mulenpay_key = decrypt_key(getattr(s, 'mulenpay_api_key', None)) if s else None
                mulenpay_secret = decrypt_key(getattr(s, 'mulenpay_secret_key', None)) if s else None
                mulenpay_shop = decrypt_key(getattr(s, 'mulenpay_shop_id', None)) if s else None
                if not mulenpay_key or not mulenpay_secret or not mulenpay_shop or mulenpay_key == "DECRYPTION_ERROR" or mulenpay_secret == "DECRYPTION_ERROR" or mulenpay_shop == "DECRYPTION_ERROR":
                    return jsonify({"message": "Mulenpay credentials not configured"}), 500
                
                currency_map = {'RUB': 'rub', 'UAH': 'uah', 'USD': 'usd'}
                mulenpay_currency = currency_map.get(info['c'], info['c'].lower())
                
                try:
                    shop_id_int = int(mulenpay_shop)
                except (ValueError, TypeError):
                    shop_id_int = mulenpay_shop
                
                payload = {
                    "currency": mulenpay_currency,
                    "amount": str(final_amount),
                    "uuid": order_id,
                    "shopId": shop_id_int,
                    "description": f"Подписка StealthNET - {t.name} ({t.duration_days} дней)",
                    "subscribe": None,
                    "holdTime": None
                }
                
                import base64
                auth_string = f"{mulenpay_key}:{mulenpay_secret}"
                auth_b64 = base64.b64encode(auth_string.encode('ascii')).decode('ascii')
                
                headers = {
                    "Authorization": f"Basic {auth_b64}",
                    "Content-Type": "application/json"
                }
                
                try:
                    resp = requests.post("https://api.mulenpay.ru/v2/payments", json=payload, headers=headers, timeout=30)
                    resp.raise_for_status()
                    payment_data = resp.json()
                    
                    payment_url = payment_data.get('url') or payment_data.get('payment_url') or payment_data.get('redirect')
                    payment_system_id = payment_data.get('id') or payment_data.get('payment_id') or order_id
                    
                    if not payment_url:
                        error_msg = payment_data.get('message') or payment_data.get('error') or 'Failed to get payment URL from Mulenpay'
                        print(f"Mulenpay Error: {error_msg}")
                        return jsonify({"message": error_msg}), 500
                except requests.exceptions.RequestException as e:
                    error_msg = str(e)
                    if hasattr(e, 'response') and e.response is not None:
                        try:
                            error_data = e.response.json()
                            error_msg = error_data.get('message') or error_data.get('error') or str(e)
                        except:
                            pass
                    return jsonify({"message": f"Mulenpay API Error: {error_msg}"}), 500
            
            # UrlPay
            elif payment_provider == 'urlpay':
                urlpay_key = decrypt_key(getattr(s, 'urlpay_api_key', None)) if s else None
                urlpay_secret = decrypt_key(getattr(s, 'urlpay_secret_key', None)) if s else None
                urlpay_shop = decrypt_key(getattr(s, 'urlpay_shop_id', None)) if s else None
                if not urlpay_key or not urlpay_secret or not urlpay_shop or urlpay_key == "DECRYPTION_ERROR" or urlpay_secret == "DECRYPTION_ERROR" or urlpay_shop == "DECRYPTION_ERROR":
                    return jsonify({"message": "UrlPay credentials not configured"}), 500
                
                currency_map = {'RUB': 'rub', 'UAH': 'uah', 'USD': 'usd'}
                urlpay_currency = currency_map.get(info['c'], info['c'].lower())
                
                try:
                    shop_id_int = int(urlpay_shop)
                except (ValueError, TypeError):
                    shop_id_int = urlpay_shop
                
                payload = {
                    "currency": urlpay_currency,
                    "amount": str(final_amount),
                    "uuid": order_id,
                    "shopId": shop_id_int,
                    "description": f"Подписка StealthNET - {t.name} ({t.duration_days} дней)",
                    "subscribe": None,
                    "holdTime": None
                }
                
                import base64
                auth_string = f"{urlpay_key}:{urlpay_secret}"
                auth_b64 = base64.b64encode(auth_string.encode('ascii')).decode('ascii')
                
                headers = {
                    "Authorization": f"Basic {auth_b64}",
                    "Content-Type": "application/json"
                }
                
                try:
                    resp = requests.post("https://api.urlpay.io/v2/payments", json=payload, headers=headers, timeout=30)
                    resp.raise_for_status()
                    payment_data = resp.json()
                    
                    payment_url = payment_data.get('url') or payment_data.get('payment_url') or payment_data.get('redirect')
                    payment_system_id = payment_data.get('id') or payment_data.get('payment_id') or order_id
                    
                    if not payment_url:
                        error_msg = payment_data.get('message') or payment_data.get('error') or 'Failed to get payment URL from UrlPay'
                        print(f"UrlPay Error: {error_msg}")
                        return jsonify({"message": error_msg}), 500
                except requests.exceptions.RequestException as e:
                    error_msg = str(e)
                    if hasattr(e, 'response') and e.response is not None:
                        try:
                            error_data = e.response.json()
                            error_msg = error_data.get('message') or error_data.get('error') or str(e)
                        except:
                            pass
                    return jsonify({"message": f"UrlPay API Error: {error_msg}"}), 500
            
            # BTCPayServer
            elif payment_provider == 'btcpayserver':
                btcpayserver_url = decrypt_key(getattr(s, 'btcpayserver_url', None)) if s else None
                btcpayserver_api_key = decrypt_key(getattr(s, 'btcpayserver_api_key', None)) if s else None
                btcpayserver_store_id = decrypt_key(getattr(s, 'btcpayserver_store_id', None)) if s else None
                if not btcpayserver_url or not btcpayserver_api_key or not btcpayserver_store_id or btcpayserver_url == "DECRYPTION_ERROR" or btcpayserver_api_key == "DECRYPTION_ERROR" or btcpayserver_store_id == "DECRYPTION_ERROR":
                    return jsonify({"message": "BTCPayServer credentials not configured"}), 500
                
                btcpayserver_url = btcpayserver_url.rstrip('/')
                
                metadata = {
                    "orderId": order_id,
                    "buyerEmail": user.email if user.email else None,
                    "itemDesc": f"VPN Subscription - {t.name} ({t.duration_days} days)"
                }
                
                checkout_options = {
                    "redirectURL": get_return_url(source='website')
                }
                
                payload = {
                    "amount": f"{final_amount:.2f}",
                    "currency": info['c'],
                    "metadata": metadata,
                    "checkout": checkout_options
                }
                
                invoice_url = f"{btcpayserver_url}/api/v1/stores/{btcpayserver_store_id}/invoices"
                
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"token {btcpayserver_api_key}"
                }
                
                try:
                    resp = requests.post(invoice_url, json=payload, headers=headers, timeout=30)
                    resp.raise_for_status()
                    invoice_data = resp.json()
                    
                    payment_url = invoice_data.get('checkoutLink')
                    payment_system_id = invoice_data.get('id')
                    
                    if not payment_url:
                        return jsonify({"message": "Failed to create payment"}), 500
                except requests.exceptions.RequestException as e:
                    error_msg = str(e)
                    if hasattr(e, 'response') and e.response is not None:
                        try:
                            error_data = e.response.json()
                            error_msg = error_data.get('message') or error_data.get('error') or str(e)
                        except:
                            pass
                    return jsonify({"message": f"BTCPayServer API Error: {error_msg}"}), 500
            
            # Tribute
            elif payment_provider == 'tribute':
                tribute_api_key = decrypt_key(getattr(s, 'tribute_api_key', None)) if s else None
                if not tribute_api_key or tribute_api_key == "DECRYPTION_ERROR":
                    return jsonify({"message": "Tribute API key not configured"}), 500
                
                currency_map = {'RUB': 'rub', 'UAH': 'rub', 'USD': 'eur'}
                tribute_currency = currency_map.get(info['c'], 'rub')
                
                amount_in_cents = int(final_amount * 100)
                
                payload = {
                    "amount": amount_in_cents,
                    "currency": tribute_currency,
                    "title": f"VPN Subscription - {t.name}"[:100],
                    "description": f"VPN subscription for {t.duration_days} days"[:300],
                    "successUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription",
                    "failUrl": f"{YOUR_SERVER_IP_OR_DOMAIN}/dashboard/subscription"
                }
                
                if user.email:
                    payload["email"] = user.email
                
                headers = {
                    "Content-Type": "application/json",
                    "Api-Key": tribute_api_key
                }
                
                try:
                    resp = requests.post("https://tribute.tg/api/v1/shop/orders", json=payload, headers=headers, timeout=30)
                    resp.raise_for_status()
                    order_data = resp.json()
                    
                    payment_url = order_data.get('paymentUrl')
                    payment_system_id = order_data.get('uuid')
                    
                    if not payment_url:
                        return jsonify({"message": "Failed to create payment"}), 500
                except requests.exceptions.RequestException as e:
                    error_msg = str(e)
                    if hasattr(e, 'response') and e.response is not None:
                        try:
                            error_data = e.response.json()
                            error_msg = error_data.get('message') or error_data.get('error') or str(e)
                        except:
                            pass
                    return jsonify({"message": f"Tribute API Error: {error_msg}"}), 500
            
            # CrystalPay по умолчанию
            else:
                crystalpay_key = decrypt_key(s.crystalpay_api_key) if s else None
                crystalpay_secret = decrypt_key(s.crystalpay_api_secret) if s else None
                if not crystalpay_key or not crystalpay_secret or crystalpay_key == "DECRYPTION_ERROR" or crystalpay_secret == "DECRYPTION_ERROR":
                    return jsonify({"message": "CrystalPay credentials not configured"}), 500
                
                # Эндпоинт /api/client/create-payment используется только с сайта
                from modules.api.payments.base import get_return_url
                redirect_url = get_return_url(source='website')
                
                payload = {
                    "auth_login": crystalpay_key,
                    "auth_secret": crystalpay_secret,
                    "amount": f"{final_amount:.2f}",
                    "type": "purchase",
                    "currency": info['c'],
                    "lifetime": 60,
                    "extra": order_id,
                    "callback_url": f"{YOUR_SERVER_IP_OR_DOMAIN}/api/webhook/crystalpay",
                    "redirect_url": redirect_url
                }
                
                resp = requests.post("https://api.crystalpay.io/v3/invoice/create/", json=payload, timeout=10)
                if resp.ok:
                    data = resp.json()
                    if not data.get('errors'):
                        payment_url = data.get('url')
                        payment_system_id = data.get('id')
                    else:
                        print(f"CrystalPay Error: {data.get('errors')}")
                else:
                    print(f"CrystalPay API Error: {resp.status_code} - {resp.text}")
            
            if not payment_url:
                return jsonify({"message": "Не удалось создать платеж"}), 500
            
            # Создаем запись о платеже
            new_p = Payment(
                order_id=order_id,
                user_id=user.id,
                tariff_id=t.id,
                status='PENDING',
                amount=final_amount,
                currency=info['c'],
                payment_system_id=str(payment_system_id) if payment_system_id else order_id,
                payment_provider=payment_provider,
                promo_code_id=promo_code_obj.id if promo_code_obj else None
            )
            db.session.add(new_p)
            db.session.commit()
            return jsonify({"payment_url": payment_url}), 200
        
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Internal Error"}), 500


# ============================================================================
# SUBSCRIPTION CONFIG
# ============================================================================

@app.route('/api/client/subscription/config', methods=['GET'])
def get_subscription_config():
    """Получить конфигурацию подписки (содержимое subscription URL)"""
    user = get_user_from_token()
    if not user:
        return jsonify({"message": "Ошибка аутентификации"}), 401
    
    try:
        # Получаем subscription URL из данных пользователя
        subscription_url = None
        
        # Пробуем получить из кэша
        cache_key = f'live_data_{user.remnawave_uuid}'
        cached = cache.get(cache_key)
        
        if cached:
            subscription_url = cached.get('subscriptionUrl')
        else:
            # Получаем из RemnaWave API
            API_URL = os.getenv('API_URL')
            headers, cookies = get_remnawave_headers()
            try:
                resp = requests.get(
                    f"{API_URL}/api/users/{user.remnawave_uuid}",
                    headers=headers,
                    cookies=cookies,
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json().get('response', {})
                    subscription_url = data.get('subscriptionUrl')
                    cache.set(cache_key, data, timeout=300)
            except Exception as e:
                print(f"Error fetching subscription URL: {e}")
        
        if not subscription_url:
            return jsonify({"message": "Подписка не найдена"}), 404
        
        # Получаем содержимое subscription URL
        try:
            resp = requests.get(subscription_url, timeout=10)
            if resp.status_code == 200:
                config_content = resp.text
                return jsonify({
                    "subscription_url": subscription_url,
                    "config": config_content
                }), 200
            else:
                return jsonify({"message": f"Не удалось получить конфигурацию: {resp.status_code}"}), 500
        except Exception as e:
            print(f"Error fetching subscription config: {e}")
            return jsonify({"message": "Ошибка при получении конфигурации"}), 500
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Internal Error"}), 500
