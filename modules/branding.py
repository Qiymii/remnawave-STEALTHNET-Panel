"""
Модуль брендинга - реэкспорт из modules.models.branding

DEPRECATED: Используйте modules.models.branding напрямую
"""
from modules.models.branding import BrandingSetting


def get_branding_settings():
    """Получить настройки брендинга"""
    return BrandingSetting.query.first()


__all__ = ['BrandingSetting', 'get_branding_settings']
