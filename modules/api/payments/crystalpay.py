"""
CrystalPay - платёжная система
https://crystalpay.io/
"""
import requests
from modules.api.payments.base import get_payment_settings, decrypt_key, get_callback_url, get_return_url


def create_crystalpay_payment(amount: float, currency: str, order_id: str, **kwargs):
    """
    Создать платёж через CrystalPay
    
    Args:
        amount: Сумма платежа
        currency: Валюта (UAH, RUB, USD)
        order_id: ID заказа
    
    Returns:
        tuple: (payment_url, payment_id) или (None, error_message)
    """
    settings = get_payment_settings()
    if not settings:
        return None, "Payment settings not configured"
    
    api_key = decrypt_key(settings.crystalpay_api_key)
    api_secret = decrypt_key(settings.crystalpay_api_secret)
    
    if not api_key or not api_secret:
        return None, "CrystalPay API credentials not configured"
    
    try:
        # Используем v3 API (как в app.py)
        payload = {
            "auth_login": api_key,
            "auth_secret": api_secret,
            "amount": f"{amount:.2f}",  # Строка с 2 знаками после запятой
            "type": "purchase",
            "currency": currency,
            "lifetime": 60,  # 60 минут как в app.py
            "extra": order_id,
            "callback_url": get_callback_url('crystalpay'),  # callback_url, а не callback
            "redirect_url": get_return_url(kwargs.get('source', 'miniapp'), kwargs.get('miniapp_type', 'v2'))
        }
        
        response = requests.post(
            "https://api.crystalpay.io/v3/invoice/create/",
            json=payload,
            timeout=30
        )
        
        data = response.json()
        
        # В v3 API ошибки приходят в поле 'errors'
        if data.get('errors'):
            return None, str(data.get('errors', 'CrystalPay API Error'))
        
        return data.get('url'), data.get('id')
        
    except requests.RequestException as e:
        return None, f"CrystalPay connection error: {str(e)}"
    except Exception as e:
        return None, f"CrystalPay error: {str(e)}"


def verify_crystalpay_signature(data: dict, signature: str) -> bool:
    """Проверить подпись webhook от CrystalPay"""
    import hashlib
    
    settings = get_payment_settings()
    if not settings:
        return False
    
    api_secret = decrypt_key(settings.crystalpay_api_secret)
    if not api_secret:
        return False
    
    # Формируем строку для подписи
    sign_string = f"{data.get('id')}:{data.get('extra')}:{api_secret}"
    calculated_signature = hashlib.sha1(sign_string.encode()).hexdigest()
    
    return calculated_signature == signature

