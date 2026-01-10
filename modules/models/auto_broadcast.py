"""
Модель для хранения текстов автоматических рассылок и настроек планировщика
"""
from modules.core import get_db

db = get_db()

class AutoBroadcastMessage(db.Model):
    __tablename__ = 'auto_broadcast_message'
    
    id = db.Column(db.Integer, primary_key=True)
    message_type = db.Column(db.String(50), unique=True, nullable=False)  # 'subscription_expiring_3days', 'trial_expiring'
    message_text = db.Column(db.Text, nullable=False)  # Текст сообщения
    enabled = db.Column(db.Boolean, default=True)  # Включена ли автоматическая рассылка
    bot_type = db.Column(db.String(10), default='both')  # 'old', 'new', 'both'
    button_text = db.Column(db.String(100), nullable=True)  # Текст кнопки
    button_url = db.Column(db.String(255), nullable=True)  # URL кнопки (webapp или ссылка)
    button_action = db.Column(db.String(50), nullable=True)  # Действие кнопки: 'webapp', 'url', 'trial'
    created_at = db.Column(db.DateTime, default=db.func.now())
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())


class AutoBroadcastSettings(db.Model):
    """Настройки планировщика автоматической рассылки"""
    __tablename__ = 'auto_broadcast_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, default=True)  # Включена ли автоматическая рассылка
    hours = db.Column(db.String(50), default='9,14,19')  # Часы запуска через запятую
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())

