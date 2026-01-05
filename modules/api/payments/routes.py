"""
API эндпоинты для платежей
"""
from flask import jsonify, request
from modules.core import get_app, get_db, get_fernet
from modules.auth import admin_required, get_user_from_token
from modules.models.payment import Payment, PaymentSetting
from modules.api.payments import create_payment, PAYMENT_PROVIDERS

app = get_app()
db = get_db()


@app.route('/api/admin/payment-settings', methods=['GET', 'POST'])
@admin_required
def payment_settings(current_admin):
    """Настройки платёжных систем"""
    try:
        s = PaymentSetting.query.first()
        if not s:
            s = PaymentSetting()
            db.session.add(s)
            db.session.commit()
            # Перезагружаем объект из БД после создания
            db.session.refresh(s)
    except Exception as e:
        print(f"Error initializing payment settings: {e}")
        import traceback
        traceback.print_exc()
        s = PaymentSetting()
        db.session.add(s)
        try:
            db.session.commit()
            db.session.refresh(s)
        except:
            db.session.rollback()
    
    def decrypt_key(key):
        """Расшифровка ключа"""
        if not key:
            return ""
        fernet = get_fernet()
        if not fernet:
            print("⚠️  Fernet не инициализирован для расшифровки")
            return ""
        try:
            # PostgreSQL может возвращать bytes или memoryview
            if isinstance(key, memoryview):
                key = bytes(key)
            elif isinstance(key, str):
                # Если строка, проверяем, зашифрована ли
                if key.startswith('gAAAAAB'):
                    return fernet.decrypt(key.encode('utf-8')).decode('utf-8')
                else:
                    # Если не зашифрована, возвращаем как есть
                    return key
            elif isinstance(key, bytes):
                # Если bytes, расшифровываем
                return fernet.decrypt(key).decode('utf-8')
            else:
                # Другие типы - пробуем преобразовать в bytes
                try:
                    key_bytes = bytes(key)
                    return fernet.decrypt(key_bytes).decode('utf-8')
                except:
                    return ""
        except Exception as e:
            print(f"⚠️  Ошибка расшифровки ключа (тип: {type(key)}): {str(e)[:100]}")
            return ""
    
    if request.method == 'GET':
        # Отладочная информация
        if s:
            print(f"🔍 GET payment-settings: PaymentSetting ID={s.id}")
            print(f"   crystalpay_api_key exists: {s.crystalpay_api_key is not None}")
            if s.crystalpay_api_key:
                print(f"   crystalpay_api_key type: {type(s.crystalpay_api_key)}")
                print(f"   crystalpay_api_key length: {len(str(s.crystalpay_api_key))}")
                print(f"   crystalpay_api_key starts with gAAAAAB: {str(s.crystalpay_api_key).startswith('gAAAAAB')}")
                decrypted = decrypt_key(s.crystalpay_api_key)
                print(f"   crystalpay_api_key decrypted length: {len(decrypted)}")
        
        return jsonify({
            # CrystalPay
            "crystalpay_api_key": decrypt_key(s.crystalpay_api_key) if s and s.crystalpay_api_key else "",
            "crystalpay_api_secret": decrypt_key(s.crystalpay_api_secret) if s and s.crystalpay_api_secret else "",
            
            # Heleket
            "heleket_api_key": decrypt_key(s.heleket_api_key),
            
            # YooKassa
            "yookassa_shop_id": decrypt_key(s.yookassa_shop_id),
            "yookassa_secret_key": decrypt_key(s.yookassa_secret_key),
            "yookassa_api_key": decrypt_key(s.yookassa_api_key),
            "yookassa_receipt_required": getattr(s, 'yookassa_receipt_required', False),
            
            # Platega
            "platega_api_key": decrypt_key(getattr(s, 'platega_api_key', None)),
            "platega_merchant_id": decrypt_key(getattr(s, 'platega_merchant_id', None)),
            
            # MulenPay
            "mulenpay_api_key": decrypt_key(getattr(s, 'mulenpay_api_key', None)),
            "mulenpay_secret_key": decrypt_key(getattr(s, 'mulenpay_secret_key', None)),
            "mulenpay_shop_id": decrypt_key(getattr(s, 'mulenpay_shop_id', None)),
            
            # URLPay
            "urlpay_api_key": decrypt_key(getattr(s, 'urlpay_api_key', None)),
            "urlpay_secret_key": decrypt_key(getattr(s, 'urlpay_secret_key', None)),
            "urlpay_shop_id": decrypt_key(getattr(s, 'urlpay_shop_id', None)),
            
            # Monobank
            "monobank_token": decrypt_key(getattr(s, 'monobank_token', None)),
            
            # BTCPayServer
            "btcpayserver_url": decrypt_key(getattr(s, 'btcpayserver_url', None)),
            "btcpayserver_api_key": decrypt_key(getattr(s, 'btcpayserver_api_key', None)),
            "btcpayserver_store_id": decrypt_key(getattr(s, 'btcpayserver_store_id', None)),
            
            # Tribute
            "tribute_api_key": decrypt_key(getattr(s, 'tribute_api_key', None)),
            
            # Robokassa
            "robokassa_merchant_login": decrypt_key(getattr(s, 'robokassa_merchant_login', None)),
            "robokassa_password1": decrypt_key(getattr(s, 'robokassa_password1', None)),
            "robokassa_password2": decrypt_key(getattr(s, 'robokassa_password2', None)),
            
            # FreeKassa
            "freekassa_shop_id": decrypt_key(s.freekassa_shop_id),
            "freekassa_secret": decrypt_key(s.freekassa_secret),
            "freekassa_secret2": decrypt_key(s.freekassa_secret2),
            
            # CryptoBot
            "cryptobot_api_key": decrypt_key(s.cryptobot_api_key),
            
            # Telegram Stars
            "telegram_bot_token": decrypt_key(s.telegram_bot_token)
        }), 200
    
    # POST - обновление
    try:
        data = request.json
        
        # Убеждаемся, что объект s существует и добавлен в сессию
        if not s:
            s = PaymentSetting()
            db.session.add(s)
        
        # Если объект новый (без id), сначала сохраняем его
        if not s.id:
            db.session.add(s)
            db.session.flush()  # Получаем id без коммита
        
        def encrypt_key(key):
            """Шифрование ключа"""
            if not key or not key.strip():
                return None
            fernet = get_fernet()
            if not fernet:
                return key  # Если нет fernet, сохраняем как есть
            try:
                # Шифруем и конвертируем в строку для PostgreSQL TEXT поля
                encrypted = fernet.encrypt(key.encode('utf-8'))
                # PostgreSQL TEXT хранит строки, поэтому конвертируем bytes в строку
                return encrypted.decode('utf-8') if isinstance(encrypted, bytes) else encrypted
            except Exception as e:
                print(f"⚠️  Ошибка шифрования ключа: {str(e)[:100]}")
                return key  # Если ошибка шифрования, сохраняем как есть
        
        # Шифруем все ключи при сохранении
        if 'crystalpay_api_key' in data:
            s.crystalpay_api_key = encrypt_key(data.get('crystalpay_api_key', ''))
        if 'crystalpay_api_secret' in data:
            s.crystalpay_api_secret = encrypt_key(data.get('crystalpay_api_secret', ''))
        if 'heleket_api_key' in data:
            s.heleket_api_key = encrypt_key(data.get('heleket_api_key', ''))
        if 'telegram_bot_token' in data:
            s.telegram_bot_token = encrypt_key(data.get('telegram_bot_token', ''))
        if 'yookassa_shop_id' in data:
            s.yookassa_shop_id = encrypt_key(data.get('yookassa_shop_id', ''))
        if 'yookassa_secret_key' in data:
            s.yookassa_secret_key = encrypt_key(data.get('yookassa_secret_key', ''))
        if 'yookassa_api_key' in data:
            s.yookassa_api_key = encrypt_key(data.get('yookassa_api_key', ''))
        if 'yookassa_receipt_required' in data:
            s.yookassa_receipt_required = bool(data.get('yookassa_receipt_required', False))
        if 'platega_api_key' in data:
            setattr(s, 'platega_api_key', encrypt_key(data.get('platega_api_key', '')))
        if 'platega_merchant_id' in data:
            setattr(s, 'platega_merchant_id', encrypt_key(data.get('platega_merchant_id', '')))
        if 'mulenpay_api_key' in data:
            setattr(s, 'mulenpay_api_key', encrypt_key(data.get('mulenpay_api_key', '')))
        if 'mulenpay_secret_key' in data:
            setattr(s, 'mulenpay_secret_key', encrypt_key(data.get('mulenpay_secret_key', '')))
        if 'mulenpay_shop_id' in data:
            setattr(s, 'mulenpay_shop_id', encrypt_key(data.get('mulenpay_shop_id', '')))
        if 'urlpay_api_key' in data:
            setattr(s, 'urlpay_api_key', encrypt_key(data.get('urlpay_api_key', '')))
        if 'urlpay_secret_key' in data:
            setattr(s, 'urlpay_secret_key', encrypt_key(data.get('urlpay_secret_key', '')))
        if 'urlpay_shop_id' in data:
            setattr(s, 'urlpay_shop_id', encrypt_key(data.get('urlpay_shop_id', '')))
        if 'monobank_token' in data:
            setattr(s, 'monobank_token', encrypt_key(data.get('monobank_token', '')))
        if 'btcpayserver_url' in data:
            setattr(s, 'btcpayserver_url', encrypt_key(data.get('btcpayserver_url', '')))
        if 'btcpayserver_api_key' in data:
            setattr(s, 'btcpayserver_api_key', encrypt_key(data.get('btcpayserver_api_key', '')))
        if 'btcpayserver_store_id' in data:
            setattr(s, 'btcpayserver_store_id', encrypt_key(data.get('btcpayserver_store_id', '')))
        if 'tribute_api_key' in data:
            setattr(s, 'tribute_api_key', encrypt_key(data.get('tribute_api_key', '')))
        if 'robokassa_merchant_login' in data:
            setattr(s, 'robokassa_merchant_login', encrypt_key(data.get('robokassa_merchant_login', '')))
        if 'robokassa_password1' in data:
            setattr(s, 'robokassa_password1', encrypt_key(data.get('robokassa_password1', '')))
        if 'robokassa_password2' in data:
            setattr(s, 'robokassa_password2', encrypt_key(data.get('robokassa_password2', '')))
        if 'freekassa_shop_id' in data:
            s.freekassa_shop_id = encrypt_key(data.get('freekassa_shop_id', ''))
        if 'freekassa_secret' in data:
            s.freekassa_secret = encrypt_key(data.get('freekassa_secret', ''))
        if 'freekassa_secret2' in data:
            s.freekassa_secret2 = encrypt_key(data.get('freekassa_secret2', ''))
        if 'cryptobot_api_key' in data:
            s.cryptobot_api_key = encrypt_key(data.get('cryptobot_api_key', ''))
        
        # Убеждаемся, что объект в сессии перед коммитом
        db.session.merge(s)  # merge гарантирует, что объект в сессии
        db.session.commit()
        
        print(f"✅ Payment settings saved successfully (ID: {s.id})")
        return jsonify({"message": "Payment settings updated successfully"}), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error updating payment settings: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": f"Internal Error: {str(e)}"}), 500


@app.route('/api/public/available-payment-methods', methods=['GET'])
def available_payment_methods():
    """Получить список доступных платёжных методов"""
    def decrypt_key(key):
        """Расшифровка ключа"""
        fernet = get_fernet()
        if not key or not fernet:
            return ""
        try:
            return fernet.decrypt(key).decode('utf-8')
        except:
            return ""
    
    try:
        s = PaymentSetting.query.first()
        if not s:
            return jsonify({"available_methods": []}), 200
        
        available = []
        
        # CrystalPay - нужны api_key и api_secret
        crystalpay_key = decrypt_key(s.crystalpay_api_key) if s.crystalpay_api_key else None
        crystalpay_secret = decrypt_key(s.crystalpay_api_secret) if s.crystalpay_api_secret else None
        if crystalpay_key and crystalpay_secret and crystalpay_key != "DECRYPTION_ERROR" and crystalpay_secret != "DECRYPTION_ERROR":
            available.append('crystalpay')
        
        # Heleket - нужен api_key
        heleket_key = decrypt_key(s.heleket_api_key) if s.heleket_api_key else None
        if heleket_key and heleket_key != "DECRYPTION_ERROR":
            available.append('heleket')
        
        # YooKassa - нужны shop_id и secret_key
        yookassa_shop = decrypt_key(s.yookassa_shop_id) if s.yookassa_shop_id else None
        yookassa_secret = decrypt_key(s.yookassa_secret_key) if s.yookassa_secret_key else None
        if yookassa_shop and yookassa_secret and yookassa_shop != "DECRYPTION_ERROR" and yookassa_secret != "DECRYPTION_ERROR":
            available.append('yookassa')
        
        # Platega - нужны api_key и merchant_id
        platega_key = decrypt_key(getattr(s, 'platega_api_key', None)) if getattr(s, 'platega_api_key', None) else None
        platega_merchant = decrypt_key(getattr(s, 'platega_merchant_id', None)) if getattr(s, 'platega_merchant_id', None) else None
        if platega_key and platega_merchant and platega_key != "DECRYPTION_ERROR" and platega_merchant != "DECRYPTION_ERROR":
            available.append('platega')
        
        # Mulenpay - нужны api_key, secret_key и shop_id
        mulenpay_key = decrypt_key(getattr(s, 'mulenpay_api_key', None)) if getattr(s, 'mulenpay_api_key', None) else None
        mulenpay_secret = decrypt_key(getattr(s, 'mulenpay_secret_key', None)) if getattr(s, 'mulenpay_secret_key', None) else None
        mulenpay_shop = decrypt_key(getattr(s, 'mulenpay_shop_id', None)) if getattr(s, 'mulenpay_shop_id', None) else None
        if mulenpay_key and mulenpay_secret and mulenpay_shop and mulenpay_key != "DECRYPTION_ERROR" and mulenpay_secret != "DECRYPTION_ERROR" and mulenpay_shop != "DECRYPTION_ERROR":
            available.append('mulenpay')
        
        # UrlPay - нужны api_key, secret_key и shop_id
        urlpay_key = decrypt_key(getattr(s, 'urlpay_api_key', None)) if getattr(s, 'urlpay_api_key', None) else None
        urlpay_secret = decrypt_key(getattr(s, 'urlpay_secret_key', None)) if getattr(s, 'urlpay_secret_key', None) else None
        urlpay_shop = decrypt_key(getattr(s, 'urlpay_shop_id', None)) if getattr(s, 'urlpay_shop_id', None) else None
        if urlpay_key and urlpay_secret and urlpay_shop and urlpay_key != "DECRYPTION_ERROR" and urlpay_secret != "DECRYPTION_ERROR" and urlpay_shop != "DECRYPTION_ERROR":
            available.append('urlpay')
        
        # Telegram Stars - нужен bot_token
        telegram_token = decrypt_key(s.telegram_bot_token) if s.telegram_bot_token else None
        if telegram_token and telegram_token != "DECRYPTION_ERROR":
            available.append('telegram_stars')
        
        # Monobank - нужен token
        monobank_token = decrypt_key(getattr(s, 'monobank_token', None)) if getattr(s, 'monobank_token', None) else None
        if monobank_token and monobank_token != "DECRYPTION_ERROR":
            available.append('monobank')
        
        # BTCPayServer - нужны url, api_key и store_id
        btcpayserver_url = decrypt_key(getattr(s, 'btcpayserver_url', None)) if getattr(s, 'btcpayserver_url', None) else None
        btcpayserver_api_key = decrypt_key(getattr(s, 'btcpayserver_api_key', None)) if getattr(s, 'btcpayserver_api_key', None) else None
        btcpayserver_store_id = decrypt_key(getattr(s, 'btcpayserver_store_id', None)) if getattr(s, 'btcpayserver_store_id', None) else None
        if btcpayserver_url and btcpayserver_api_key and btcpayserver_store_id and btcpayserver_url != "DECRYPTION_ERROR" and btcpayserver_api_key != "DECRYPTION_ERROR" and btcpayserver_store_id != "DECRYPTION_ERROR":
            available.append('btcpayserver')
        
        # Tribute - нужен api_key
        tribute_api_key = decrypt_key(getattr(s, 'tribute_api_key', None)) if getattr(s, 'tribute_api_key', None) else None
        if tribute_api_key and tribute_api_key != "DECRYPTION_ERROR":
            available.append('tribute')
        
        # Robokassa - нужны merchant_login и password1
        robokassa_login = decrypt_key(getattr(s, 'robokassa_merchant_login', None)) if getattr(s, 'robokassa_merchant_login', None) else None
        robokassa_password1 = decrypt_key(getattr(s, 'robokassa_password1', None)) if getattr(s, 'robokassa_password1', None) else None
        if robokassa_login and robokassa_password1 and robokassa_login != "DECRYPTION_ERROR" and robokassa_password1 != "DECRYPTION_ERROR":
            available.append('robokassa')
        
        # Freekassa - нужны shop_id и secret
        freekassa_shop_id = decrypt_key(s.freekassa_shop_id) if s.freekassa_shop_id else None
        freekassa_secret = decrypt_key(s.freekassa_secret) if s.freekassa_secret else None
        if freekassa_shop_id and freekassa_secret and freekassa_shop_id != "DECRYPTION_ERROR" and freekassa_secret != "DECRYPTION_ERROR":
            available.append('freekassa')
        
        # CryptoBot - нужен api_key
        cryptobot_api_key = decrypt_key(s.cryptobot_api_key) if s.cryptobot_api_key else None
        if cryptobot_api_key and cryptobot_api_key != "DECRYPTION_ERROR":
            available.append('cryptobot')
        
        return jsonify({"available_methods": available}), 200
        
    except Exception as e:
        print(f"Error in available_payment_methods: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"available_methods": []}), 200

