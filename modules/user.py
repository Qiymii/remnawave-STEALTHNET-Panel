"""
Модуль пользователей - реэкспорт из modules.models.user

DEPRECATED: Используйте modules.models.user напрямую
"""
from modules.models.user import User

# Функции для обратной совместимости
def get_user_by_email(email):
    """Получить пользователя по email"""
    return User.query.filter_by(email=email).first()

def get_user_by_telegram_id(telegram_id):
    """Получить пользователя по Telegram ID"""
    return User.query.filter_by(telegram_id=telegram_id).first()

def create_user(**kwargs):
    """Создать нового пользователя"""
    from modules.core import get_db
    db = get_db()
    user = User(**kwargs)
    db.session.add(user)
    db.session.commit()
    return user

__all__ = ['User', 'get_user_by_email', 'get_user_by_telegram_id', 'create_user']
