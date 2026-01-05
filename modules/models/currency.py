"""
Модель курсов валют
"""
from datetime import datetime, timezone
from modules.core import get_db

db = get_db()

class CurrencyRate(db.Model):
    """Курс валюты"""
    id = db.Column(db.Integer, primary_key=True)
    currency = db.Column(db.String(10), unique=True, nullable=False)  # 'UAH', 'RUB', 'USD'
    rate_to_usd = db.Column(db.Float, nullable=False)  # Курс к USD
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))


def get_currency_rate(currency):
    """Получить курс валюты к USD"""
    rate = CurrencyRate.query.filter_by(currency=currency.upper()).first()
    if rate:
        return rate.rate_to_usd
    # Дефолтные курсы
    defaults = {'UAH': 41.0, 'RUB': 95.0, 'USD': 1.0, 'EUR': 0.92}
    return defaults.get(currency.upper(), 1.0)


def convert_to_usd(amount, from_currency):
    """Конвертировать в USD"""
    rate = get_currency_rate(from_currency)
    return amount / rate


def convert_from_usd(amount_usd, to_currency):
    """Конвертировать из USD"""
    rate = get_currency_rate(to_currency)
    return amount_usd * rate

