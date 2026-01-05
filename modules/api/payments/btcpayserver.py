"""
BTCPay Server - self-hosted платёжная система для криптовалют
https://btcpayserver.org/
"""
import requests
from modules.api.payments.base import get_payment_settings, decrypt_key, get_callback_url, get_return_url


def create_btcpayserver_payment(amount: float, currency: str, order_id: str, **kwargs):
    """
    Создать платёж через BTCPay Server
    
    Args:
        amount: Сумма платежа
        currency: Валюта
        order_id: ID заказа
        user_email: Email пользователя (опционально)
    
    Returns:
        tuple: (payment_url, invoice_id) или (None, error_message)
    """
    settings = get_payment_settings()
    if not settings:
        return None, "Payment settings not configured"
    
    server_url = settings.btcpayserver_url
    api_key = decrypt_key(settings.btcpayserver_api_key)
    store_id = settings.btcpayserver_store_id
    
    if not server_url or not api_key or not store_id:
        return None, "BTCPay Server not configured"
    
    try:
        # Убираем trailing slash
        server_url = server_url.rstrip('/')
        
        payload = {
            "amount": str(amount),
            "currency": currency.upper(),
            "metadata": {
                "orderId": order_id
            },
            "checkout": {
                "redirectURL": get_return_url(kwargs.get('source', 'miniapp'), kwargs.get('miniapp_type', 'v2')),
                "redirectAutomatically": True
            },
            "receipt": {
                "enabled": True
            }
        }
        
        user_email = kwargs.get('user_email')
        if user_email:
            payload["buyer"] = {"email": user_email}
        
        headers = {
            "Authorization": f"token {api_key}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            f"{server_url}/api/v1/stores/{store_id}/invoices",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        data = response.json()
        
        if response.status_code not in [200, 201]:
            return None, data.get('message', 'BTCPay Server API Error')
        
        return data.get('checkoutLink'), data.get('id')
        
    except requests.RequestException as e:
        return None, f"BTCPay Server connection error: {str(e)}"
    except Exception as e:
        return None, f"BTCPay Server error: {str(e)}"


