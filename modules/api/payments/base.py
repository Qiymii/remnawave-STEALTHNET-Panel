"""
Базовые функции для платёжных систем
"""
import os
from modules.core import get_fernet
from modules.models.payment import PaymentSetting
from modules.models.bot_config import BotConfig

fernet = get_fernet()


def get_payment_settings():
    """Получить настройки платёжных систем"""
    return PaymentSetting.query.first()


def decrypt_key(encrypted_key):
    """Расшифровать ключ API"""
    if not encrypted_key:
        return ""
    if not fernet:
        # Если fernet не инициализирован, возвращаем как есть (если это уже строка)
        return str(encrypted_key) if encrypted_key else ""
    
    try:
        # PostgreSQL может возвращать bytes или memoryview
        if isinstance(encrypted_key, memoryview):
            encrypted_key = bytes(encrypted_key)
        elif isinstance(encrypted_key, str):
            # Если строка, проверяем, зашифрована ли (начинается с gAAAAAB)
            if encrypted_key.startswith('gAAAAAB'):
                # Зашифрована - расшифровываем
                return fernet.decrypt(encrypted_key.encode('utf-8')).decode('utf-8')
            else:
                # Не зашифрована - возвращаем как есть
                return encrypted_key
        elif isinstance(encrypted_key, bytes):
            # Если bytes, расшифровываем
            return fernet.decrypt(encrypted_key).decode('utf-8')
        else:
            # Другие типы - пробуем преобразовать в bytes
            try:
                key_bytes = bytes(encrypted_key)
                return fernet.decrypt(key_bytes).decode('utf-8')
            except:
                return str(encrypted_key) if encrypted_key else ""
    except Exception as e:
        # Если расшифровка не удалась, возвращаем пустую строку
        print(f"[DECRYPT] Failed to decrypt key: {type(encrypted_key)}, error: {str(e)[:100]}")
        return ""


def get_callback_url(provider: str) -> str:
    """Получить URL для webhook"""
    base_url = os.getenv('YOUR_SERVER_IP') or os.getenv('YOUR_SERVER_IP_OR_DOMAIN', '')
    if not base_url.startswith(('http://', 'https://')):
        base_url = f"https://{base_url}" if base_url else ""
    return f"{base_url}/api/webhook/{provider}" if base_url else f"/api/webhook/{provider}"


def get_bot_username() -> str:
    """Получить username бота для deep links"""
    # ВАЖНО: TELEGRAM_BOT_NAME_V2 имеет высший приоритет
    # Сначала проверяем переменные окружения (TELEGRAM_BOT_NAME_V2 имеет приоритет)
    bot_username = os.getenv('TELEGRAM_BOT_NAME_V2') or os.getenv('TELEGRAM_BOT_NAME') or os.getenv('BOT_USERNAME') or os.getenv('CLIENT_BOT_USERNAME')
    if bot_username:
        if bot_username.startswith('@'):
            bot_username = bot_username[1:]
        return bot_username
    
    # Если нет в переменных окружения, пробуем получить из BotConfig
    try:
        bot_config = BotConfig.query.first()
        if bot_config and bot_config.bot_username:
            username = bot_config.bot_username
            # Убираем @ если есть
            if username.startswith('@'):
                username = username[1:]
            return username
    except:
        pass
    
    return ''


def get_return_url(source='miniapp', miniapp_type='v2') -> str:
    """
    Получить URL для возврата после оплаты
    
    Args:
        source: 'miniapp' для мини-апп (возврат в бот) или 'website' для сайта (возврат на сайт)
        miniapp_type: 'v2' для нового мини-аппа, 'v1' или 'old' для старого мини-аппа
    """
    # Сначала пробуем YOUR_SERVER_IP, потом YOUR_SERVER_IP_OR_DOMAIN
    base_url = os.getenv('YOUR_SERVER_IP') or os.getenv('YOUR_SERVER_IP_OR_DOMAIN', '')
    if not base_url:
        # Если нет base_url, возвращаем относительный путь
        if source == 'website':
            return "/dashboard/subscription"
        # Для старого мини-аппа используем /miniapp/payment-success.html
        if miniapp_type in ('v1', 'old'):
            return "/miniapp/payment-success.html"
        return "/payment-success.html"

    # Убеждаемся, что есть протокол
    if not base_url.startswith(('http://', 'https://')):
        base_url = f"https://{base_url}"

    # Для сайта возвращаем на страницу подписки
    if source == 'website':
        return f"{base_url}/dashboard/subscription"

    # Для старого мини-аппа используем /miniapp/payment-success.html
    if miniapp_type in ('v1', 'old'):
        bot_username = get_bot_username() or 'stealthnet_test_bot'
        return f"{base_url}/miniapp/payment-success.html?bot={bot_username}"

    # Для нового мини-апп используем специальную страницу успешной оплаты с автоматическим редиректом в бот
    bot_username = get_bot_username() or 'stealthnet_test_bot'
    return f"{base_url}/payment-success.html?bot={bot_username}"


def get_telegram_deep_link() -> str:
    """Получить Telegram deep link для возврата в мини-апп"""
    bot_username = get_bot_username()
    if not bot_username:
        return ''
    
    base_url = os.getenv('YOUR_SERVER_IP') or os.getenv('YOUR_SERVER_IP_OR_DOMAIN', '')
    if not base_url:
        return ''
    
    # Убеждаемся, что есть протокол
    if not base_url.startswith(('http://', 'https://')):
        base_url = f"https://{base_url}"
    
    miniapp_url = f"{base_url}/miniapp-v2/?payment_success=1"
    
    # Формируем deep link для открытия Web App
    # Формат: tg://resolve?domain=bot_username&startapp=miniapp_url
    # Или: https://t.me/bot_username/miniapp?startapp=miniapp_url
    deep_link = f"tg://resolve?domain={bot_username}&startapp={miniapp_url}"
    
    return deep_link

