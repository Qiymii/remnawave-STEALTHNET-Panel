"""
Модуль системных настроек - реэкспорт из modules.models.system

DEPRECATED: Используйте modules.models.system напрямую
"""
from modules.models.system import SystemSetting
from modules.core import get_app, get_db

# Реэкспорт для обратной совместимости
app = get_app()
db = get_db()


def get_system_settings():
    """Получить системные настройки"""
    return SystemSetting.query.first()


def create_system_settings():
    """Создать настройки по умолчанию"""
    settings = SystemSetting(
        default_language='ru',
        default_currency='uah'
    )
    db.session.add(settings)
    db.session.commit()
    return settings


__all__ = ['SystemSetting', 'get_system_settings', 'create_system_settings', 'app', 'db']
