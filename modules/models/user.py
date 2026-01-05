"""
Модель пользователя
"""
from datetime import datetime, timezone
from modules.core import get_db
from sqlalchemy import event
import os
import requests

db = get_db()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(128), nullable=True)
    encrypted_password = db.Column(db.Text, nullable=True)
    role = db.Column(db.String(20), nullable=False, default='CLIENT')
    remnawave_uuid = db.Column(db.String(100), nullable=True)
    referral_code = db.Column(db.String(20), unique=True, nullable=True)
    referrer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    is_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(100), nullable=True)
    balance = db.Column(db.Float, default=0.0)
    referral_percent = db.Column(db.Float, default=10.0)  # Процент реферала (по умолчанию 10%)
    preferred_lang = db.Column(db.String(5), default='ru')
    preferred_currency = db.Column(db.String(5), default='uah')
    telegram_id = db.Column(db.String(50), unique=True, nullable=True)
    telegram_username = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    
    # Блокировка аккаунта
    is_blocked = db.Column(db.Boolean, default=False, nullable=False)
    block_reason = db.Column(db.Text, nullable=True)
    blocked_at = db.Column(db.DateTime, nullable=True)
    
    # Связь с реферером
    referrer = db.relationship('User', remote_side=[id], backref='referrals')


# Автоматическая синхронизация telegramId в RemnaWave при изменении telegram_id
from sqlalchemy import event
import os
import requests

@event.listens_for(User, 'after_update')
def sync_telegram_id_to_remnawave(mapper, connection, target):
    """Автоматически синхронизирует telegramId в RemnaWave при изменении telegram_id"""
    # Проверяем, изменился ли telegram_id
    history = db.inspect(target).attrs.telegram_id.history
    if history.has_changes() and target.remnawave_uuid:
        old_value = history.deleted[0] if history.deleted else None
        new_value = target.telegram_id
        
        # Если значение изменилось, обновляем в RemnaWave
        if old_value != new_value:
            try:
                API_URL = os.getenv('API_URL')
                ADMIN_TOKEN = os.getenv('ADMIN_TOKEN')
                
                if API_URL and ADMIN_TOKEN:
                    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
                    requests.patch(
                        f"{API_URL}/api/users",
                        headers=headers,
                        json={"uuid": target.remnawave_uuid, "telegramId": str(new_value) if new_value else None},
                        timeout=10
                    )
                    print(f"✓ Synced telegramId to RemnaWave for user {target.id}: {old_value} -> {new_value}")
            except Exception as e:
                print(f"Warning: Failed to sync telegramId to RemnaWave for user {target.id}: {e}")

