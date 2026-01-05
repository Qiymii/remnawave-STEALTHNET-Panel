"""
Модуль конфигурации бота - реэкспорт из modules.models.bot_config

DEPRECATED: Используйте modules.models.bot_config напрямую
"""
from modules.models.bot_config import BotConfig


def get_bot_config():
    """Получить конфигурацию бота"""
    return BotConfig.query.first()


__all__ = ['BotConfig', 'get_bot_config']
