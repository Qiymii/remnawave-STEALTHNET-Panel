"""
Модели платежей и настроек платёжных систем
"""
from datetime import datetime, timezone
from modules.core import get_db, get_fernet

db = get_db()
fernet = get_fernet()

class PaymentSetting(db.Model):
    """Настройки платёжных систем"""
    id = db.Column(db.Integer, primary_key=True)
    
    # CrystalPay
    crystalpay_api_key = db.Column(db.Text, nullable=True)
    crystalpay_api_secret = db.Column(db.Text, nullable=True)
    
    # Heleket
    heleket_api_key = db.Column(db.Text, nullable=True)
    
    # Telegram Stars
    telegram_bot_token = db.Column(db.Text, nullable=True)
    
    # YooKassa
    yookassa_api_key = db.Column(db.Text, nullable=True)
    yookassa_shop_id = db.Column(db.Text, nullable=True)
    yookassa_secret_key = db.Column(db.Text, nullable=True)
    yookassa_receipt_required = db.Column(db.Boolean, default=False, nullable=False)  # Требовать receipt (чек) при создании платежа
    
    # CryptoBot
    cryptobot_api_key = db.Column(db.Text, nullable=True)
    
    # Platega
    platega_api_key = db.Column(db.Text, nullable=True)
    platega_merchant_id = db.Column(db.Text, nullable=True)
    
    # MulenPay
    mulenpay_api_key = db.Column(db.Text, nullable=True)
    mulenpay_secret_key = db.Column(db.Text, nullable=True)
    mulenpay_shop_id = db.Column(db.Text, nullable=True)
    
    # URLPay
    urlpay_api_key = db.Column(db.Text, nullable=True)
    urlpay_secret_key = db.Column(db.Text, nullable=True)
    urlpay_shop_id = db.Column(db.Text, nullable=True)
    
    # Monobank
    monobank_token = db.Column(db.Text, nullable=True)
    
    # BTCPayServer
    btcpayserver_url = db.Column(db.Text, nullable=True)
    btcpayserver_api_key = db.Column(db.Text, nullable=True)
    btcpayserver_store_id = db.Column(db.Text, nullable=True)
    
    # Tribute
    tribute_api_key = db.Column(db.Text, nullable=True)
    
    # Robokassa
    robokassa_merchant_login = db.Column(db.Text, nullable=True)
    robokassa_password1 = db.Column(db.Text, nullable=True)
    robokassa_password2 = db.Column(db.Text, nullable=True)
    
    # FreeKassa
    freekassa_shop_id = db.Column(db.Text, nullable=True)
    freekassa_secret = db.Column(db.Text, nullable=True)
    freekassa_secret2 = db.Column(db.Text, nullable=True)


class Payment(db.Model):
    """Платёж"""
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(100), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tariff_id = db.Column(db.Integer, db.ForeignKey('tariff.id'), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='PENDING')
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(5), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    payment_system_id = db.Column(db.String(100), nullable=True)
    payment_provider = db.Column(db.String(20), nullable=True, default='crystalpay')
    promo_code_id = db.Column(db.Integer, db.ForeignKey('promo_code.id'), nullable=True)
    telegram_message_id = db.Column(db.Integer, nullable=True)  # ID сообщения в Telegram боте о создании платежа


def decrypt_key(key):
    """Расшифровка ключа"""
    if not key or not fernet:
        return ""
    try:
        return fernet.decrypt(key).decode('utf-8')
    except Exception:
        return ""


