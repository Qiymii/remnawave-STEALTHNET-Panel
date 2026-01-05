"""
Модель конфигурации Telegram бота
"""
from datetime import datetime, timezone
from modules.core import get_db

db = get_db()

class BotConfig(db.Model):
    """Конфигурация Telegram бота"""
    id = db.Column(db.Integer, primary_key=True)
    service_name = db.Column(db.String(100), default='StealthNET', nullable=False)
    bot_username = db.Column(db.String(100), nullable=True)
    support_url = db.Column(db.String(500), nullable=True)
    support_bot_username = db.Column(db.String(100), nullable=True)
    
    # Видимость кнопок
    show_webapp_button = db.Column(db.Boolean, default=True, nullable=False)
    show_trial_button = db.Column(db.Boolean, default=True, nullable=False)
    show_referral_button = db.Column(db.Boolean, default=True, nullable=False)
    show_support_button = db.Column(db.Boolean, default=True, nullable=False)
    show_servers_button = db.Column(db.Boolean, default=True, nullable=False)
    show_agreement_button = db.Column(db.Boolean, default=True, nullable=False)
    show_offer_button = db.Column(db.Boolean, default=True, nullable=False)
    show_topup_button = db.Column(db.Boolean, default=True, nullable=False)
    
    # Триал
    trial_days = db.Column(db.Integer, default=3, nullable=False)
    
    # Переводы
    translations_ru = db.Column(db.Text, nullable=True)
    translations_ua = db.Column(db.Text, nullable=True)
    translations_en = db.Column(db.Text, nullable=True)
    translations_cn = db.Column(db.Text, nullable=True)
    
    # Приветственные сообщения
    welcome_message_ru = db.Column(db.Text, nullable=True)
    welcome_message_ua = db.Column(db.Text, nullable=True)
    welcome_message_en = db.Column(db.Text, nullable=True)
    welcome_message_cn = db.Column(db.Text, nullable=True)
    
    # Пользовательские соглашения
    user_agreement_ru = db.Column(db.Text, nullable=True)
    user_agreement_ua = db.Column(db.Text, nullable=True)
    user_agreement_en = db.Column(db.Text, nullable=True)
    user_agreement_cn = db.Column(db.Text, nullable=True)
    
    # Оферта
    offer_text_ru = db.Column(db.Text, nullable=True)
    offer_text_ua = db.Column(db.Text, nullable=True)
    offer_text_en = db.Column(db.Text, nullable=True)
    offer_text_cn = db.Column(db.Text, nullable=True)
    
    # Структура меню
    menu_structure = db.Column(db.Text, nullable=True)
    
    # Подписка на канал
    require_channel_subscription = db.Column(db.Boolean, default=False, nullable=False)
    channel_id = db.Column(db.String(100), nullable=True)
    channel_url = db.Column(db.String(500), nullable=True)
    channel_subscription_text_ru = db.Column(db.Text, nullable=True)
    channel_subscription_text_ua = db.Column(db.Text, nullable=True)
    channel_subscription_text_en = db.Column(db.Text, nullable=True)
    channel_subscription_text_cn = db.Column(db.Text, nullable=True)
    
    # Ссылка на бота
    bot_link_for_miniapp = db.Column(db.String(500), nullable=True)
    buttons_order = db.Column(db.Text, nullable=True)
    
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))


def get_bot_config():
    """Получить конфигурацию бота"""
    return BotConfig.query.first()


