"""
Robokassa - платёжная система
https://robokassa.com/
"""
import hashlib
from modules.api.payments.base import get_payment_settings, decrypt_key


def create_robokassa_payment(amount: float, currency: str, order_id: str, **kwargs):
    """
    Создать платёж через Robokassa
    
    Args:
        amount: Сумма платежа
        currency: Валюта
        order_id: ID заказа
        description: Описание платежа
    
    Returns:
        tuple: (payment_url, order_id) или (None, error_message)
    """
    settings = get_payment_settings()
    if not settings:
        return None, "Payment settings not configured"
    
    merchant_login = settings.robokassa_merchant_login
    password1 = decrypt_key(settings.robokassa_password1)
    
    if not merchant_login or not password1:
        return None, "Robokassa credentials not configured"
    
    try:
        description = kwargs.get('description', f'Подписка StealthNET #{order_id}')
        
        # Robokassa работает с RUB
        out_sum = f"{amount:.2f}"
        
        # Формируем подпись
        sign_string = f"{merchant_login}:{out_sum}:{order_id}:{password1}"
        signature = hashlib.md5(sign_string.encode()).hexdigest()
        
        # Формируем URL
        payment_url = (
            f"https://auth.robokassa.ru/Merchant/Index.aspx"
            f"?MerchantLogin={merchant_login}"
            f"&OutSum={out_sum}"
            f"&InvId={order_id}"
            f"&Description={description}"
            f"&SignatureValue={signature}"
            f"&IsTest=0"
        )
        
        return payment_url, order_id
        
    except Exception as e:
        return None, f"Robokassa error: {str(e)}"


def verify_robokassa_signature(data: dict) -> bool:
    """Проверить подпись webhook от Robokassa"""
    settings = get_payment_settings()
    if not settings:
        return False
    
    password2 = decrypt_key(settings.robokassa_password2)
    if not password2:
        return False
    
    # Формируем подпись для проверки (Result URL)
    sign_string = f"{data.get('OutSum')}:{data.get('InvId')}:{password2}"
    calculated_signature = hashlib.md5(sign_string.encode()).hexdigest().upper()
    
    return calculated_signature == data.get('SignatureValue', '').upper()


