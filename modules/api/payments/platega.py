"""
Platega - платёжная система
https://docs.platega.io/
"""
import requests
import uuid
import time
from modules.api.payments.base import get_payment_settings, decrypt_key, get_callback_url, get_return_url

# Глобальная сессия для сохранения cookies между запросами (для обхода DDoS-Guard)
_platega_session = None
_platega_cookies_initialized = False

def _get_platega_session():
    """Получить или создать сессию для Platega"""
    global _platega_session, _platega_cookies_initialized
    if _platega_session is None:
        _platega_session = requests.Session()
        _platega_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })
    
    # Предварительный запрос для получения cookies от DDoS-Guard (только один раз)
    if not _platega_cookies_initialized:
        try:
            print("Platega: Initializing DDoS-Guard cookies...")
            # Делаем GET запрос к главной странице для получения cookies
            _platega_session.get("https://app.platega.io/", timeout=10)
            _platega_cookies_initialized = True
            print("Platega: DDoS-Guard cookies initialized")
        except Exception as e:
            print(f"Platega: Warning - failed to initialize cookies: {e}")
            # Продолжаем работу даже если не удалось получить cookies
    
    return _platega_session

def _reset_platega_cookies():
    """Сбросить cookies Platega и получить новые"""
    global _platega_cookies_initialized
    session = _get_platega_session()
    _platega_cookies_initialized = False
    session.cookies.clear()
    try:
        session.get("https://app.platega.io/", timeout=10)
        _platega_cookies_initialized = True
        print("Platega: New DDoS-Guard cookies obtained")
        return True
    except Exception as e:
        print(f"Platega: Failed to get new cookies: {e}")
        return False


def create_platega_payment(amount: float, currency: str, order_id: str, **kwargs):
    """
    Создать платёж через Platega
    
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
    
    api_key = decrypt_key(getattr(settings, 'platega_api_key', None))
    merchant_id = decrypt_key(getattr(settings, 'platega_merchant_id', None))
    
    if not api_key or api_key == "DECRYPTION_ERROR":
        return None, "Platega API key not configured"
    
    if not merchant_id or merchant_id == "DECRYPTION_ERROR":
        return None, "Platega Merchant ID not configured"
    
    if not isinstance(api_key, str) or not api_key.strip():
        return None, "Platega API key is empty"
    
    if not isinstance(merchant_id, str) or not merchant_id.strip():
        return None, "Platega Merchant ID is empty"
    
    try:
        transaction_uuid = str(uuid.uuid4())
        
        # URL для возврата после оплаты
        return_url = get_return_url(kwargs.get('source', 'miniapp'), kwargs.get('miniapp_type', 'v2'))
        
        # Согласно документации Platega:
        # - ID транзакции генерируется автоматически (не передаём)
        # - paymentMethod: 2 = card
        # - amount должен быть float
        payload = {
            "paymentMethod": 2,
            "paymentDetails": {
                "amount": float(amount),
                "currency": currency
            },
            "description": f"Payment for order {order_id}",
            "return": return_url,
            "failedUrl": return_url
        }
        
        headers = {
            "Content-Type": "application/json",
            "X-MerchantId": merchant_id,
            "X-Secret": api_key,
            # Заголовки для обхода DDoS-Guard
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Origin": "https://app.platega.io",
            "Referer": "https://app.platega.io/"
        }
        
        # Логируем для диагностики (без полных ключей)
        print(f"Platega request: merchant_id={merchant_id[:10] if merchant_id else 'N/A'}... (len={len(merchant_id) if merchant_id else 0}), key_len={len(api_key) if api_key else 0}, order_id={order_id}")
        print(f"Platega headers: X-MerchantId present={bool(merchant_id)}, X-Secret present={bool(api_key)}")
        
        # Используем сессию для сохранения cookies между запросами
        session = _get_platega_session()
        
        # Пробуем сначала использовать API endpoint (без DDoS-Guard)
        api_endpoints = [
            "https://api.platega.io/transaction/process",  # API endpoint (может быть без DDoS-Guard)
            "https://app.platega.io/transaction/process"  # Web endpoint (с DDoS-Guard)
        ]
        
        response = None
        last_error = None
        
        for endpoint in api_endpoints:
            try:
                print(f"Platega: Trying endpoint {endpoint}...")
                # Добавляем небольшую задержку между попытками
                if response is not None:
                    time.sleep(1)
                
                response = session.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                
                # Если получили успешный ответ, используем этот endpoint
                if response.status_code == 200:
                    print(f"Platega: Success with {endpoint}")
                    break
                elif response.status_code != 403:
                    # Если не 403, значит endpoint работает, но есть другая ошибка
                    break
                else:
                    # 403 - пробуем следующий endpoint
                    last_error = response
                    print(f"Platega: Got 403 from {endpoint}, trying next...")
                    continue
                    
            except Exception as e:
                print(f"Platega: Error with {endpoint}: {e}")
                last_error = e
                continue
        
        if response is None:
            if last_error:
                return None, f"Platega connection error: {str(last_error)}"
            return None, "Platega: Failed to connect to any endpoint"
        
        print(f"Platega response: status={response.status_code}")
        if response.status_code != 200:
            print(f"Platega error response: {response.text[:500]}")
        
        # Если получили 401, проверяем заголовки
        if response.status_code == 401:
            print(f"Platega 401 Unauthorized - проверьте X-MerchantId и X-Secret")
            print(f"Platega request headers sent: X-MerchantId={'present' if 'X-MerchantId' in headers else 'missing'}, X-Secret={'present' if 'X-Secret' in headers else 'missing'}")
            return None, f"Platega API Error: 401 Unauthorized - проверьте правильность X-MerchantId и X-Secret. Response: {response.text[:200]}"
        
        # Если получили 403 от DDoS-Guard, сбрасываем cookies и пробуем снова
        if response.status_code == 403:
            response_text = response.text[:200] if response.text else ""
            if "DDoS-Guard" in response_text or "ddos-guard" in response_text.lower():
                print("Platega: DDoS-Guard challenge detected, resetting session and retrying...")
                if _reset_platega_cookies():
                    # Повторяем запрос
                    response = session.post(
                        "https://app.platega.io/transaction/process",
                        json=payload,
                        headers=headers,
                        timeout=30
                    )
                    print(f"Platega retry response: status={response.status_code}")
            
            # Если все еще 403, возвращаем ошибку
            if response.status_code == 403:
                response_text = response.text[:500] if response.text else ""
                if "DDoS-Guard" in response_text or "ddos-guard" in response_text.lower():
                    error_msg = (
                        "Platega заблокировал запрос через DDoS-Guard. "
                        "Для решения проблемы необходимо добавить IP сервера в whitelist Platega. "
                        "Свяжитесь с поддержкой Platega и предоставьте IP: 192.3.209.113"
                    )
                else:
                    try:
                        error_data = response.json()
                        error_msg = error_data.get('message') or error_data.get('error') or 'Forbidden - Invalid credentials'
                        print(f"Platega 403 Error: {error_data}")
                    except:
                        error_msg = response_text or 'Forbidden - Invalid credentials'
                return None, error_msg
        
        # Проверяем 401 до raise_for_status()
        if response.status_code == 401:
            error_text = response.text[:500] if response.text else ""
            print(f"Platega 401 Unauthorized - проверьте X-MerchantId и X-Secret")
            print(f"Platega request headers sent: X-MerchantId={'present' if 'X-MerchantId' in headers else 'missing'}, X-Secret={'present' if 'X-Secret' in headers else 'missing'}")
            return None, f"Platega API Error: 401 Unauthorized - проверьте правильность X-MerchantId и X-Secret. Response: {error_text}"
        
        response.raise_for_status()
        data = response.json()
        
        print(f"Platega response data: {data}")
        
        # Согласно документации Platega: URL в поле "redirect", ID в "transactionId"
        payment_url = data.get('redirect') or data.get('url') or data.get('paymentUrl')
        payment_id = data.get('transactionId') or data.get('id') or transaction_uuid
        
        if not payment_url:
            print(f"Platega: No redirect URL in response: {data}")
            return None, "Platega did not return payment URL"
        
        return payment_url, payment_id
        
    except requests.exceptions.HTTPError as e:
        print(f"Platega HTTP Error: {e}")
        return None, f"Platega API Error: {str(e)}"
    except requests.RequestException as e:
        print(f"Platega connection error: {e}")
        return None, f"Platega connection error: {str(e)}"
    except Exception as e:
        print(f"Platega error: {e}")
        return None, f"Platega error: {str(e)}"


def verify_platega_signature(data: dict, signature: str) -> bool:
    """Проверить подпись webhook от Platega"""
    # Platega может использовать собственный механизм проверки
    # На данный момент просто возвращаем True
    # TODO: Добавить проверку подписи согласно документации Platega
    return True

