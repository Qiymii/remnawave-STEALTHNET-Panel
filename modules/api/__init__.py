"""
API модули StealthNET

Структура:
- auth/      - Авторизация и регистрация
- admin/     - Административные эндпоинты
- client/    - Клиентские эндпоинты
- public/    - Публичные эндпоинты
- payments/  - Платежи и платежные системы
- webhooks/  - Вебхуки платежных систем
- miniapp/   - Telegram Mini App
- support/   - Поддержка и тикеты
- bot/       - Интеграция с Telegram ботом
"""

def register_all_routes():
    """Регистрирует все маршруты API"""
    # Импортируем все модули маршрутов
    from modules.api.auth import routes as auth_routes
    from modules.api.admin import routes as admin_routes
    from modules.api.client import routes as client_routes
    from modules.api.public import routes as public_routes
    from modules.api.payments import routes as payment_routes
    from modules.api.webhooks import routes as webhook_routes
    from modules.api.miniapp import routes as miniapp_routes
    from modules.api.support import routes as support_routes
    from modules.api.bot import routes as bot_routes
