"""
Платёжные системы StealthNET

Каждая платёжная система в отдельном файле:
- crystalpay.py   - CrystalPay
- heleket.py      - Heleket
- yookassa.py     - YooKassa
- telegram_stars.py - Telegram Stars
- freekassa.py    - FreeKassa
- robokassa.py    - Robokassa
- cryptobot.py    - CryptoBot
- monobank.py     - Monobank
- btcpayserver.py - BTCPayServer
- platega.py      - Platega
"""

from modules.api.payments.crystalpay import create_crystalpay_payment
from modules.api.payments.heleket import create_heleket_payment
from modules.api.payments.yookassa import create_yookassa_payment
from modules.api.payments.telegram_stars import create_telegram_stars_payment
from modules.api.payments.freekassa import create_freekassa_payment
from modules.api.payments.robokassa import create_robokassa_payment
from modules.api.payments.cryptobot import create_cryptobot_payment
from modules.api.payments.monobank import create_monobank_payment
from modules.api.payments.btcpayserver import create_btcpayserver_payment
from modules.api.payments.platega import create_platega_payment

# Маппинг провайдеров к функциям создания платежа
PAYMENT_PROVIDERS = {
    'crystalpay': create_crystalpay_payment,
    'heleket': create_heleket_payment,
    'yookassa': create_yookassa_payment,
    'telegram_stars': create_telegram_stars_payment,
    'freekassa': create_freekassa_payment,
    'robokassa': create_robokassa_payment,
    'cryptobot': create_cryptobot_payment,
    'monobank': create_monobank_payment,
    'btcpayserver': create_btcpayserver_payment,
    'platega': create_platega_payment,
}


def create_payment(provider: str, amount: float, currency: str, order_id: str, **kwargs):
    """
    Универсальная функция создания платежа
    
    Args:
        provider: Название платёжной системы
        amount: Сумма платежа
        currency: Валюта
        order_id: ID заказа
        **kwargs: Дополнительные параметры
    
    Returns:
        tuple: (url, payment_id) или (None, error_message)
    """
    if provider not in PAYMENT_PROVIDERS:
        return None, f"Unknown payment provider: {provider}"
    
    return PAYMENT_PROVIDERS[provider](amount, currency, order_id, **kwargs)


