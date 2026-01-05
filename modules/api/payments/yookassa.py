"""
YooKassa (ЮKassa) - платёжная система
https://yookassa.ru/
"""
import requests
import uuid
import json
from modules.api.payments.base import get_payment_settings, decrypt_key, get_callback_url, get_return_url


def create_yookassa_payment(amount: float, currency: str, order_id: str, **kwargs):
    """
    Создать платёж через YooKassa
    
    Args:
        amount: Сумма платежа
        currency: Валюта (RUB)
        order_id: ID заказа
        user_email: Email пользователя (опционально)
    
    Returns:
        tuple: (payment_url, payment_id) или (None, error_message)
    """
    settings = get_payment_settings()
    if not settings:
        return None, "Payment settings not configured"
    
    # Оба ключа должны быть расшифрованы
    shop_id = decrypt_key(settings.yookassa_shop_id) if settings.yookassa_shop_id else None
    secret_key = decrypt_key(settings.yookassa_secret_key) if settings.yookassa_secret_key else None
    
    # Если расшифровка не удалась, decrypt_key вернет пустую строку
    if not shop_id or not secret_key:
        print(f"[YOOKASSA] Credentials check: shop_id exists={bool(settings.yookassa_shop_id)}, secret_key exists={bool(settings.yookassa_secret_key)}")
        print(f"[YOOKASSA] Credentials check: shop_id decrypted={bool(shop_id)}, secret_key decrypted={bool(secret_key)}")
        return None, "YooKassa credentials not configured or decryption failed"
    
    # Проверяем формат shop_id (должен быть числом или строкой с цифрами)
    # YooKassa shop_id обычно выглядит как число или UUID
    if not shop_id.strip() or len(shop_id.strip()) < 3:
        print(f"[YOOKASSA] Invalid shop_id format: '{shop_id}' (length: {len(shop_id) if shop_id else 0})")
        return None, "YooKassa shop_id has invalid format"
    
    if not secret_key.strip() or len(secret_key.strip()) < 10:
        print(f"[YOOKASSA] Invalid secret_key format: length={len(secret_key) if secret_key else 0}")
        return None, "YooKassa secret_key has invalid format"
    
    try:
        # YooKassa работает только с RUB
        yookassa_currency = 'RUB'
        
        payload = {
            "amount": {
                "value": f"{amount:.2f}",
                "currency": yookassa_currency
            },
            "confirmation": {
                "type": "redirect",
                "return_url": get_return_url(kwargs.get('source', 'miniapp'), kwargs.get('miniapp_type', 'v2'))
            },
            "capture": True,
            "description": kwargs.get('description', f"Подписка StealthNET #{order_id}"),
            "metadata": {
                "order_id": order_id
            }
        }
        
        # Проверяем настройку receipt из базы данных
        receipt_required = getattr(settings, 'yookassa_receipt_required', False) or kwargs.get('receipt_required', False)
        user_email = kwargs.get('user_email')
        
        # Добавляем receipt если:
        # 1. Настройка receipt_required=True в админ-панели
        # 2. ИЛИ есть email пользователя (на случай, если в настройках магазина YooKassa включена обязательная отправка чеков)
        # Согласно документации YooKassa, если в настройках магазина включена обязательная отправка чеков,
        # receipt должен быть в каждом платеже. Поэтому всегда добавляем receipt, если есть email.
        if receipt_required or user_email:
            if not user_email:
                # Если receipt обязателен в настройках, но email нет - это ошибка
                if receipt_required:
                    print(f"[YOOKASSA] Error: receipt_required=True but no user_email provided. Receipt cannot be created.")
                    return None, "Email is required for receipt generation. Please provide user email."
                # Если receipt не обязателен в настройках и нет email - не добавляем receipt
            else:
                # Формируем receipt правильно согласно документации YooKassa (54-ФЗ)
                # https://yookassa.ru/developers/payment-acceptance/receipts/54fz/yoomoney/payments
                # https://yookassa.ru/developers/payment-acceptance/receipts/54fz/yoomoney/parameters-values
                receipt_items = kwargs.get('receipt_items', [{
                    "description": kwargs.get('description', f"Подписка StealthNET #{order_id}"),
                    "quantity": "1.00",  # Обязательно строка с двумя знаками после точки
                    "amount": {
                        "value": f"{amount:.2f}",  # Обязательно строка с двумя знаками после точки
                        "currency": yookassa_currency
                    },
                    "vat_code": kwargs.get('vat_code', 1),  # 1 = НДС не облагается, 11 = НДС 22%, 12 = НДС 22/122%
                    "payment_mode": kwargs.get('payment_mode', 'full_payment'),  # full_payment = полный расчет
                    "payment_subject": kwargs.get('payment_subject', 'service')  # service = услуга
                }])
                
                payload["receipt"] = {
                    "customer": {
                        "email": user_email  # Обязательно для отправки чека
                    },
                    "items": receipt_items
                }
                print(f"[YOOKASSA] Receipt added: email={user_email}, vat_code={receipt_items[0].get('vat_code', 1)}")
        
        headers = {
            "Content-Type": "application/json",
            "Idempotence-Key": str(uuid.uuid4())
        }
        
        response = requests.post(
            "https://api.yookassa.ru/v3/payments",
            json=payload,
            headers=headers,
            auth=(shop_id, secret_key),
            timeout=30
        )
        
        try:
            data = response.json()
        except:
            data = {"description": f"HTTP {response.status_code}: {response.text[:200]}"}
        
        if response.status_code != 200:
            error_msg = data.get('description') or data.get('message') or f"YooKassa API Error: {response.status_code}"
            print(f"[YOOKASSA] Payment creation failed: {error_msg}")
            print(f"[YOOKASSA] Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
            return None, error_msg
        
        confirmation = data.get('confirmation', {})
        return confirmation.get('confirmation_url'), data.get('id')
        
    except requests.RequestException as e:
        return None, f"YooKassa connection error: {str(e)}"
    except Exception as e:
        return None, f"YooKassa error: {str(e)}"


