"""
Модуль платежей - реэкспорт из modules.models.payment

DEPRECATED: Используйте modules.models.payment напрямую
"""
from modules.models.payment import Payment, PaymentSetting, decrypt_key
from modules.core import get_db, get_fernet
import uuid
import os
import requests

db = get_db()


def create_payment(user_id, tariff_id, payment_provider, amount, currency, promo_code_id=None):
    """Создать платёж"""
    order_id = f"SN-{uuid.uuid4().hex[:12].upper()}"
    
    payment = Payment(
        order_id=order_id,
        user_id=user_id,
        tariff_id=tariff_id,
        amount=amount,
        currency=currency,
        payment_provider=payment_provider,
        promo_code_id=promo_code_id,
        status='PENDING'
    )
    
    db.session.add(payment)
    db.session.commit()
    
    return payment, order_id


def create_heleket_payment(amount, currency, order_id, email):
    """Создать платёж Heleket"""
    try:
        s = PaymentSetting.query.first()
        if not s or not s.heleket_api_key:
            return None, "Heleket not configured"
        
        api_key = decrypt_key(s.heleket_api_key)
        if not api_key:
            return None, "Invalid Heleket API key"
        
        # TODO: Реализовать вызов Heleket API
        return f"https://heleket.com/pay/{order_id}", order_id
        
    except Exception as e:
        return None, str(e)


def create_telegram_stars_payment(amount, currency, order_id, email):
    """Создать платёж Telegram Stars"""
    try:
        s = PaymentSetting.query.first()
        if not s or not s.telegram_bot_token:
            return None, "Telegram Stars not configured"
        
        bot_token = decrypt_key(s.telegram_bot_token)
        if not bot_token:
            return None, "Invalid Telegram bot token"
        
        # Возвращаем URL для бота
        return f"tg://stars?order_id={order_id}", order_id
        
    except Exception as e:
        return None, str(e)


__all__ = [
    'Payment', 'PaymentSetting', 'decrypt_key',
    'create_payment', 'create_heleket_payment', 'create_telegram_stars_payment'
]
