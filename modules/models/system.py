"""
Модель системных настроек
"""
from modules.core import get_db

db = get_db()

class SystemSetting(db.Model):
    """Системные настройки"""
    id = db.Column(db.Integer, primary_key=True)
    default_language = db.Column(db.String(10), default='ru', nullable=False)
    default_currency = db.Column(db.String(10), default='uah', nullable=False)
    show_language_currency_switcher = db.Column(db.Boolean, default=True, nullable=False)
    active_languages = db.Column(db.Text, default='["ru","ua","en","cn"]', nullable=False)
    active_currencies = db.Column(db.Text, default='["uah","rub","usd"]', nullable=False)
    
    # Цветовая тема (светлая)
    theme_primary_color = db.Column(db.String(20), default='#3f69ff', nullable=False)
    theme_bg_primary = db.Column(db.String(20), default='#f8fafc', nullable=False)
    theme_bg_secondary = db.Column(db.String(20), default='#eef2ff', nullable=False)
    theme_text_primary = db.Column(db.String(20), default='#0f172a', nullable=False)
    theme_text_secondary = db.Column(db.String(20), default='#64748b', nullable=False)
    
    # Цветовая тема (тёмная)
    theme_primary_color_dark = db.Column(db.String(20), default='#6c7bff', nullable=False)
    theme_bg_primary_dark = db.Column(db.String(20), default='#050816', nullable=False)
    theme_bg_secondary_dark = db.Column(db.String(20), default='#0f172a', nullable=False)
    theme_text_primary_dark = db.Column(db.String(20), default='#e2e8f0', nullable=False)
    theme_text_secondary_dark = db.Column(db.String(20), default='#94a3b8', nullable=False)


def get_system_settings():
    """Получить системные настройки"""
    return SystemSetting.query.first()


