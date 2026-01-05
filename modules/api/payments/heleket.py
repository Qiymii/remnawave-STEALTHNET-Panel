"""
Heleket - платёжная система для криптовалют
https://heleket.com/
"""
import requests
from modules.api.payments.base import get_payment_settings, decrypt_key, get_callback_url, get_return_url


def create_heleket_payment(amount: float, currency: str, order_id: str, **kwargs):
    """
    Создать платёж через Heleket
    
    Args:
        amount: Сумма платежа
        currency: Валюта
        order_id: ID заказа
    
    Returns:
        tuple: (payment_url, payment_id) или (None, error_message)
    """
    settings = get_payment_settings()
    if not settings:
        return None, "Payment settings not configured"
    
    api_key = decrypt_key(settings.heleket_api_key)
    if not api_key:
        return None, "Heleket API key not configured"
    
    try:
        # Конвертируем в USD для Heleket
        heleket_currency = "USD"
        to_currency = "USDT" if currency != 'USD' else None
        
        payload = {
            "amount": f"{amount:.2f}",
            "currency": heleket_currency,
            "order_id": order_id,
            "url_return": get_return_url(kwargs.get('source', 'miniapp'), kwargs.get('miniapp_type', 'v2')),
            "url_callback": get_callback_url('heleket')
        }
        
        if to_currency:
            payload["to_currency"] = to_currency
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            "https://api.heleket.com/v1/payment",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        data = response.json()
        
        if data.get('state') != 0 or not data.get('result'):
            return None, data.get('message', 'Heleket API Error')
        
        result = data.get('result', {})
        return result.get('url'), result.get('uuid')
        
    except requests.RequestException as e:
        return None, f"Heleket connection error: {str(e)}"
    except Exception as e:
        return None, f"Heleket error: {str(e)}"


def verify_heleket_signature(data: dict, signature: str) -> bool:
    """Проверить подпись webhook от Heleket"""
    # Heleket использует другой метод верификации
    # TODO: Реализовать проверку подписи
    return True


