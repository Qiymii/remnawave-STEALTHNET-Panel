"""
Модуль реферальной программы - реэкспорт из modules.models.referral

DEPRECATED: Используйте modules.models.referral напрямую
"""
from modules.models.referral import ReferralSetting


def get_referral_settings():
    """Получить настройки рефералов"""
    return ReferralSetting.query.first()


__all__ = ['ReferralSetting', 'get_referral_settings']
