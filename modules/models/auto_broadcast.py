"""
Модель для хранения текстов автоматических рассылок
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
    created_at = db.Column(db.DateTime, default=db.func.now())
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())

