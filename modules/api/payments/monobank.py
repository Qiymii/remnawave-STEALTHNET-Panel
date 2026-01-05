"""
Monobank - платёжная система (Украина)
https://api.monobank.ua/
"""
import requests
from modules.api.payments.base import get_payment_settings, decrypt_key, get_callback_url, get_return_url


def create_monobank_payment(amount: float, currency: str, order_id: str, **kwargs):
    """
    Создать платёж через Monobank Acquiring
    
    Args:
        amount: Сумма платежа
        currency: Валюта (UAH)
        order_id: ID заказа
    
    Returns:
        tuple: (payment_url, invoice_id) или (None, error_message)
    """
    settings = get_payment_settings()
    if not settings:
        return None, "Payment settings not configured"
    
    token = decrypt_key(settings.monobank_token)
    if not token:
        return None, "Monobank token not configured"
    
    try:
        # Monobank работает с UAH, сумма в копейках
        amount_kopecks = int(amount * 100)
        
        payload = {
            "amount": amount_kopecks,
            "ccy": 980,  # UAH ISO код
            "merchantPaymInfo": {
                "reference": order_id,
                "destination": f"Подписка StealthNET #{order_id}"
            },
            "redirectUrl": get_return_url(kwargs.get('source', 'miniapp'), kwargs.get('miniapp_type', 'v2')),
            "webHookUrl": get_callback_url('monobank'),
            "validity": 3600  # 1 час
        }
        
        headers = {
            "X-Token": token,
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            "https://api.monobank.ua/api/merchant/invoice/create",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        data = response.json()
        
        if response.status_code != 200:
            return None, data.get('errText', 'Monobank API Error')
        
        return data.get('pageUrl'), data.get('invoiceId')
        
    except requests.RequestException as e:
        return None, f"Monobank connection error: {str(e)}"
    except Exception as e:
        return None, f"Monobank error: {str(e)}"


