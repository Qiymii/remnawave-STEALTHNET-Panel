"""
CryptoBot - платёжная система Telegram
https://t.me/CryptoBot
"""
import requests
from modules.api.payments.base import get_payment_settings, decrypt_key, get_callback_url


def create_cryptobot_payment(amount: float, currency: str, order_id: str, **kwargs):
    """
    Создать платёж через CryptoBot
    
    Args:
        amount: Сумма платежа
        currency: Валюта
        order_id: ID заказа
    
    Returns:
        tuple: (payment_url, invoice_id) или (None, error_message)
    """
    settings = get_payment_settings()
    if not settings:
        return None, "Payment settings not configured"
    
    api_key = decrypt_key(settings.cryptobot_api_key)
    if not api_key:
        return None, "CryptoBot API key not configured"
    
    try:
        # CryptoBot работает с криптовалютами
        # Используем USDT как основную валюту
        crypto_currency = "USDT"
        
        payload = {
            "asset": crypto_currency,
            "amount": str(amount),
            "description": f"Подписка StealthNET #{order_id}",
            "hidden_message": order_id,
            "payload": order_id,
            "allow_comments": False,
            "allow_anonymous": True
        }
        
        headers = {
            "Crypto-Pay-API-Token": api_key,
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            "https://pay.crypt.bot/api/createInvoice",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        data = response.json()
        
        if not data.get('ok'):
            error = data.get('error', {})
            return None, error.get('name', 'CryptoBot API Error')
        
        result = data.get('result', {})
        return result.get('pay_url'), str(result.get('invoice_id'))
        
    except requests.RequestException as e:
        return None, f"CryptoBot connection error: {str(e)}"
    except Exception as e:
        return None, f"CryptoBot error: {str(e)}"


def verify_cryptobot_signature(data: dict, signature: str) -> bool:
    """Проверить подпись webhook от CryptoBot"""
    import hashlib
    import hmac
    
    settings = get_payment_settings()
    if not settings:
        return False
    
    api_key = decrypt_key(settings.cryptobot_api_key)
    if not api_key:
        return False
    
    # CryptoBot использует HMAC-SHA256
    secret = hashlib.sha256(api_key.encode()).digest()
    check_string = str(data)
    
    calculated = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return calculated == signature


