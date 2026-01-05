"""
Модель настроек брендинга
"""
from modules.core import get_db

db = get_db()

class BrandingSetting(db.Model):
    """Настройки брендинга"""
    id = db.Column(db.Integer, primary_key=True)
    
    # Основные настройки
    logo_url = db.Column(db.String(500), nullable=True)
    favicon_url = db.Column(db.String(500), nullable=True)
    site_name = db.Column(db.String(100), default='StealthNET', nullable=False)
    site_subtitle = db.Column(db.String(200), nullable=True)
    
    # Тексты для авторизации
    login_welcome_text = db.Column(db.String(200), nullable=True)
    register_welcome_text = db.Column(db.String(200), nullable=True)
    footer_text = db.Column(db.String(200), nullable=True)
    
    # Дашборд - секции
    dashboard_servers_title = db.Column(db.String(200), nullable=True)
    dashboard_servers_description = db.Column(db.String(300), nullable=True)
    dashboard_tariffs_title = db.Column(db.String(200), nullable=True)
    dashboard_tariffs_description = db.Column(db.String(300), nullable=True)
    dashboard_tagline = db.Column(db.String(100), nullable=True)
    dashboard_referrals_title = db.Column(db.String(200), nullable=True)
    dashboard_referrals_description = db.Column(db.String(300), nullable=True)
    dashboard_support_title = db.Column(db.String(200), nullable=True)
    dashboard_support_description = db.Column(db.String(300), nullable=True)
    
    # Названия для тарифов
    tariff_tier_basic_name = db.Column(db.String(100), nullable=True)  # Название для basic tier
    tariff_tier_pro_name = db.Column(db.String(100), nullable=True)    # Название для pro tier
    tariff_tier_elite_name = db.Column(db.String(100), nullable=True)  # Название для elite tier
    
    # Названия функций тарифов (JSON для кастомизации)
    tariff_features_names = db.Column(db.Text, nullable=True)  # JSON: {"Безлимитный трафик": "Неограниченный интернет", ...}
    
    # Тексты кнопок
    button_subscribe_text = db.Column(db.String(50), nullable=True)
    button_buy_text = db.Column(db.String(50), nullable=True)
    button_connect_text = db.Column(db.String(50), nullable=True)
    button_share_text = db.Column(db.String(50), nullable=True)
    button_copy_text = db.Column(db.String(50), nullable=True)
    
    # Мета-теги
    meta_title = db.Column(db.String(200), nullable=True)
    meta_description = db.Column(db.String(500), nullable=True)
    meta_keywords = db.Column(db.String(300), nullable=True)
    
    # Быстрое скачивание
    quick_download_enabled = db.Column(db.Boolean, default=True, nullable=False)
    quick_download_windows_url = db.Column(db.String(500), nullable=True)
    quick_download_android_url = db.Column(db.String(500), nullable=True)
    quick_download_macos_url = db.Column(db.String(500), nullable=True)
    quick_download_ios_url = db.Column(db.String(500), nullable=True)
    quick_download_profile_deeplink = db.Column(db.String(200), nullable=True, default='stealthnet://install-config?url=')
    
    # Дополнительные тексты
    subscription_active_text = db.Column(db.String(200), nullable=True)
    subscription_expired_text = db.Column(db.String(200), nullable=True)
    subscription_trial_text = db.Column(db.String(200), nullable=True)
    balance_label_text = db.Column(db.String(50), nullable=True)
    referral_code_label_text = db.Column(db.String(50), nullable=True)


def get_branding_settings():
    """Получить настройки брендинга"""
    return BrandingSetting.query.first()


