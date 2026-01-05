"""
Telegram Stars - оплата через Telegram
https://core.telegram.org/bots/payments
"""
import requests
from modules.api.payments.base import get_payment_settings, decrypt_key


def create_telegram_stars_payment(amount: float, currency: str, order_id: str, **kwargs):
    """
    Создать платёж через Telegram Stars
    
    Args:
        amount: Сумма платежа
        currency: Валюта
        order_id: ID заказа
    
    Returns:
        tuple: (invoice_link, order_id) или (None, error_message)
    """
    settings = get_payment_settings()
    if not settings:
        return None, "Payment settings not configured"
    
    bot_token = decrypt_key(settings.telegram_bot_token)
    if not bot_token:
        return None, "Telegram Bot Token not configured"
    
    try:
        # Конвертируем сумму в Stars
        # Примерные курсы: 1 Star ≈ $0.01
        if currency == 'UAH':
            stars_amount = int(amount * 2.7)
        elif currency == 'RUB':
            stars_amount = int(amount * 1.1)
        elif currency == 'USD':
            stars_amount = int(amount * 100)
        else:
            stars_amount = int(amount * 100)
        
        if stars_amount < 1:
            stars_amount = 1
        
        payload = {
            "title": "Подписка StealthNET",
            "description": "Подписка на VPN сервис",
            "payload": order_id,
            "provider_token": "",  # Пустой для Stars
            "currency": "XTR",  # Telegram Stars
            "prices": [{
                "label": "Подписка",
                "amount": stars_amount
            }]
        }
        
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/createInvoiceLink",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        data = response.json()
        
        if not data.get('ok'):
            return None, data.get('description', 'Telegram API Error')
        
        return data.get('result'), order_id
        
    except requests.RequestException as e:
        return None, f"Telegram connection error: {str(e)}"
    except Exception as e:
        return None, f"Telegram Stars error: {str(e)}"


