"""
Модуль промокодов - реэкспорт из modules.models.promo

DEPRECATED: Используйте modules.models.promo напрямую
"""
from modules.models.promo import PromoCode


def apply_promo_code(promo_code, amount):
    """Применить промокод к сумме"""
    promo = PromoCode.query.filter_by(code=promo_code.upper()).first()
    if not promo or promo.uses_left <= 0:
        return amount, None
    
    if promo.promo_type == 'PERCENT':
        discount = (promo.value / 100.0) * amount
        return max(0, amount - discount), promo
    
    return amount, promo


__all__ = ['PromoCode', 'apply_promo_code']
