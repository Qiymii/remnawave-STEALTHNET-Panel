"""
Модуль валют - реэкспорт из modules.models.currency

DEPRECATED: Используйте modules.models.currency напрямую
"""
from modules.models.currency import CurrencyRate
from datetime import datetime


# Курсы валют по умолчанию (к USD) - сколько единиц валюты за 1 USD
DEFAULT_RATES = {
    'USD': 1.0,
    'UAH': 41.0,  # 1 USD = 41 UAH
    'RUB': 95.0,  # 1 USD = 95 RUB
    'EUR': 0.92,  # 1 USD = 0.92 EUR
    'GBP': 0.79   # 1 USD = 0.79 GBP
}


def get_currency_rate(currency):
    """Получить курс валюты к USD (сколько единиц валюты за 1 USD)"""
    rate = CurrencyRate.query.filter_by(currency=currency.upper()).first()
    if rate:
        return rate.rate_to_usd
    return DEFAULT_RATES.get(currency.upper(), 1.0)


def convert_to_usd(amount, from_currency):
    """Конвертировать в USD"""
    rate = get_currency_rate(from_currency)
    if rate and rate != 0:
        return amount / rate  # Если 1 USD = 41 UAH, то 100 UAH = 100/41 = 2.44 USD
    return amount


def convert_from_usd(amount_usd, to_currency):
    """Конвертировать из USD"""
    rate = get_currency_rate(to_currency)
    if rate and rate != 0:
        return amount_usd * rate  # Если 1 USD = 41 UAH, то 2.44 USD = 2.44*41 = 100 UAH
    return amount_usd


def parse_iso_datetime(date_str):
    """Парсит ISO datetime строку"""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except:
        return None


__all__ = [
    'CurrencyRate',
    'get_currency_rate',
    'convert_to_usd',
    'convert_from_usd',
    'parse_iso_datetime'
]
