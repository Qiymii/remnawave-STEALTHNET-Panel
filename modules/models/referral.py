"""
Модель реферальных настроек
"""
from modules.core import get_db

db = get_db()

class ReferralSetting(db.Model):
    """Настройки реферальной программы"""
    id = db.Column(db.Integer, primary_key=True)
    invitee_bonus_days = db.Column(db.Integer, default=3)
    referrer_bonus_days = db.Column(db.Integer, default=3)
    trial_squad_id = db.Column(db.String(100), nullable=True)
    referral_type = db.Column(db.String(20), default='DAYS')  # 'DAYS' или 'PERCENT'
    default_referral_percent = db.Column(db.Float, default=10.0)  # Процент по умолчанию для новой системы


def get_referral_settings():
    """Получить настройки реферальной программы"""
    return ReferralSetting.query.first()


