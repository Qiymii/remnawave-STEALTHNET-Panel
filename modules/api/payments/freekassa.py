"""
FreeKassa - платёжная система
https://freekassa.ru/
"""
import hashlib
from modules.api.payments.base import get_payment_settings, decrypt_key, get_callback_url


def create_freekassa_payment(amount: float, currency: str, order_id: str, **kwargs):
    """
    Создать платёж через FreeKassa
    
    Args:
        amount: Сумма платежа
        currency: Валюта
        order_id: ID заказа
    
    Returns:
        tuple: (payment_url, order_id) или (None, error_message)
    """
    settings = get_payment_settings()
    if not settings:
        return None, "Payment settings not configured"
    
    shop_id = settings.freekassa_shop_id
    secret = decrypt_key(settings.freekassa_secret)
    
    if not shop_id or not secret:
        return None, "FreeKassa credentials not configured"
    
    try:
        # FreeKassa работает с RUB
        fk_currency = 'RUB'
        
        # Формируем подпись
        sign_string = f"{shop_id}:{amount:.2f}:{secret}:{fk_currency}:{order_id}"
        signature = hashlib.md5(sign_string.encode()).hexdigest()
        
        # Формируем URL
        payment_url = (
            f"https://pay.freekassa.ru/"
            f"?m={shop_id}"
            f"&oa={amount:.2f}"
            f"&currency={fk_currency}"
            f"&o={order_id}"
            f"&s={signature}"
        )
        
        return payment_url, order_id
        
    except Exception as e:
        return None, f"FreeKassa error: {str(e)}"


def verify_freekassa_signature(data: dict) -> bool:
    """Проверить подпись webhook от FreeKassa"""
    settings = get_payment_settings()
    if not settings:
        return False
    
    secret2 = decrypt_key(settings.freekassa_secret2)
    if not secret2:
        return False
    
    # Формируем подпись для проверки
    sign_string = f"{data.get('MERCHANT_ID')}:{data.get('AMOUNT')}:{secret2}:{data.get('MERCHANT_ORDER_ID')}"
    calculated_signature = hashlib.md5(sign_string.encode()).hexdigest()
    
    return calculated_signature == data.get('SIGN')


