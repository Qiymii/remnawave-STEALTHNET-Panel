"""
Модуль для отправки уведомлений админам в Telegram группу
"""
import os
import requests
import threading
from datetime import datetime, timezone


def send_admin_notification(text: str, bot_token: str = None):
    """
    Отправить уведомление в группу админов
    
    Args:
        text: Текст уведомления (HTML формат)
        bot_token: Токен бота для отправки (если None, используется ADMIN_GROUP_BOT_TOKEN)
    """
    group_id = os.getenv("ADMIN_GROUP_ID")
    if not group_id:
        return False, "ADMIN_GROUP_ID not set"
    
    if not bot_token:
        bot_token = os.getenv("ADMIN_GROUP_BOT_TOKEN")
    
    if not bot_token:
        # Пробуем использовать токены ботов как fallback
        bot_token = os.getenv("CLIENT_BOT_V2_TOKEN") or os.getenv("CLIENT_BOT_TOKEN")
    
    if not bot_token:
        return False, "No bot token available"
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": group_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            return True, response.json().get('result', {}).get('message_id')
        else:
            error_data = response.json() if response.content else {}
            error_msg = error_data.get('description', f'HTTP {response.status_code}')
            return False, error_msg
    except Exception as e:
        return False, str(e)


def send_admin_notification_async(text: str, bot_token: str = None):
    """Отправить уведомление асинхронно (в фоне)"""
    def send():
        send_admin_notification(text, bot_token)
    
    threading.Thread(target=send, daemon=True).start()


def notify_new_user(user, registration_source="website"):
    """
    Уведомить о новом пользователе
    
    Args:
        user: Объект User
        registration_source: "website", "bot_old", "bot_new"
    """
    source_names = {
        "website": "🌐 Сайт",
        "bot_old": "🤖 Старый бот",
        "bot_new": "🤖 Новый бот"
    }
    
    source_name = source_names.get(registration_source, "❓ Неизвестно")
    
    # Формируем информацию о пользователе
    user_info = []
    if user.email:
        user_info.append(f"📧 Email: {user.email}")
    if user.telegram_id:
        user_info.append(f"🆔 Telegram ID: {user.telegram_id}")
    if user.telegram_username:
        user_info.append(f"👤 Username: @{user.telegram_username}")
    if user.referrer_id:
        referrer = user.referrer_id
        user_info.append(f"🎁 Реферал: ID {referrer}")
    
    user_info_text = "\n".join(user_info) if user_info else "Нет дополнительной информации"
    
    text = f"""
<b>🆕 Новый пользователь</b>

{source_name}

{user_info_text}

🆔 ID: {user.id}
📅 Дата: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')}
"""
    
    # Отправляем в оба бота (если доступны)
    old_bot_token = os.getenv("CLIENT_BOT_TOKEN")
    new_bot_token = os.getenv("CLIENT_BOT_V2_TOKEN")
    
    if old_bot_token:
        send_admin_notification_async(text, old_bot_token)
    
    if new_bot_token and new_bot_token != old_bot_token:
        send_admin_notification_async(text, new_bot_token)


def notify_payment(payment, user, tariff=None, is_balance_topup=False):
    """
    Уведомить о покупке/пополнении
    
    Args:
        payment: Объект Payment
        user: Объект User
        tariff: Объект Tariff (если покупка тарифа)
        is_balance_topup: True если пополнение баланса
    """
    if is_balance_topup:
        text = f"""
<b>💰 Пополнение баланса</b>

👤 Пользователь: {user.email or f'ID {user.id}'}
💵 Сумма: {payment.amount} {payment.currency}
💳 Провайдер: {payment.payment_provider or 'Неизвестно'}
🆔 Платеж: #{payment.id}

📅 Дата: {payment.created_at.strftime('%d.%m.%Y %H:%M') if payment.created_at else 'Неизвестно'}
"""
    else:
        tariff_name = tariff.name if tariff else f"Тариф #{payment.tariff_id}"
        text = f"""
<b>🛒 Покупка тарифа</b>

👤 Пользователь: {user.email or f'ID {user.id}'}
📦 Тариф: {tariff_name}
💵 Сумма: {payment.amount} {payment.currency}
💳 Провайдер: {payment.payment_provider or 'Неизвестно'}
🆔 Платеж: #{payment.id}

📅 Дата: {payment.created_at.strftime('%d.%m.%Y %H:%M') if payment.created_at else 'Неизвестно'}
"""
    
    # Отправляем в оба бота (если доступны)
    old_bot_token = os.getenv("CLIENT_BOT_TOKEN")
    new_bot_token = os.getenv("CLIENT_BOT_V2_TOKEN")
    
    if old_bot_token:
        send_admin_notification_async(text, old_bot_token)
    
    if new_bot_token and new_bot_token != old_bot_token:
        send_admin_notification_async(text, new_bot_token)


def notify_support_ticket(ticket, user, message_text=None, is_new_ticket=False):
    """
    Уведомить о новом тикете или ответе пользователя в техподдержке
    
    Args:
        ticket: Объект Ticket
        user: Объект User (создатель тикета или отправитель сообщения)
        message_text: Текст сообщения (если ответ)
        is_new_ticket: True если новый тикет, False если ответ
    """
    if is_new_ticket:
        text = f"""
<b>🎫 Новый тикет поддержки</b>

👤 Пользователь: {user.email or f'ID {user.id}'}
📧 Email: {user.email or 'Не указан'}
🆔 Telegram ID: {user.telegram_id or 'Не указан'}
📝 Тема: {ticket.subject}
💬 Сообщение: {message_text[:200] if message_text else 'Без сообщения'}{'...' if message_text and len(message_text) > 200 else ''}

🆔 Тикет: #{ticket.id}
📅 Дата: {ticket.created_at.strftime('%d.%m.%Y %H:%M') if ticket.created_at else 'Неизвестно'}
"""
    else:
        text = f"""
<b>💬 Новый ответ в тикете</b>

👤 Пользователь: {user.email or f'ID {user.id}'}
📝 Тема: {ticket.subject}
💬 Ответ: {message_text[:200] if message_text else 'Без текста'}{'...' if message_text and len(message_text) > 200 else ''}

🆔 Тикет: #{ticket.id}
📅 Дата: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')}
"""
    
    # Отправляем в оба бота (если доступны)
    old_bot_token = os.getenv("CLIENT_BOT_TOKEN")
    new_bot_token = os.getenv("CLIENT_BOT_V2_TOKEN")
    
    if old_bot_token:
        send_admin_notification_async(text, old_bot_token)
    
    if new_bot_token and new_bot_token != old_bot_token:
        send_admin_notification_async(text, new_bot_token)


def send_user_payment_notification(user, is_successful=True, tariff_name=None, is_balance_topup=False, payment_order_id=None, payment=None):
    """
    Отправить уведомление пользователю в бот о результате оплаты
    
    Args:
        user: Объект User
        is_successful: True если оплата успешна, False если неуспешна
        tariff_name: Название тарифа (если покупка тарифа)
        is_balance_topup: True если пополнение баланса
        payment_order_id: order_id платежа для удаления старого сообщения
        payment: Объект Payment (опционально, для получения telegram_message_id)
    """
    if not user.telegram_id:
        return False, "User has no telegram_id"
    
    # Получаем payment объект, если не передан
    if payment is None and payment_order_id:
        try:
            from modules.models.payment import Payment
            payment = Payment.query.filter_by(order_id=payment_order_id).first()
        except Exception as e:
            print(f"Error getting payment: {e}")
    
    # Определяем тексты сообщений
    if is_successful:
        if is_balance_topup:
            text = "✅ **Пополнение баланса успешно!**\n\n"
            text += "💰 Ваш баланс пополнен.\n\n"
        else:
            text = "✅ **Оплата успешна!**\n\n"
            if tariff_name:
                text += f"📦 Тариф: {tariff_name}\n\n"
            text += "🎉 Подписка активирована!\n\n"
        text += "━━━━━━━━━━━━━━━\n\n"
        text += "🔙 Вернуться в главное меню:"
    else:
        text = "❌ **Оплата не успешна**\n\n"
        text += "⚠️ Произошла ошибка при обработке платежа.\n\n"
        text += "Пожалуйста, повторите попытку еще раз.\n\n"
        text += "━━━━━━━━━━━━━━━\n\n"
        text += "🔙 Вернуться в главное меню:"
    
    # Формируем клавиатуру с кнопкой "Главное меню"
    keyboard = {
        "inline_keyboard": [
            [{"text": "🔙 Главное меню", "callback_data": "main_menu"}]
        ]
    }
    
    # Пробуем отправить в оба бота
    old_bot_token = os.getenv("CLIENT_BOT_TOKEN")
    new_bot_token = os.getenv("CLIENT_BOT_V2_TOKEN")
    
    success = False
    error_msg = None
    
    # Сначала пробуем старый бот
    if old_bot_token:
        try:
            url = f"https://api.telegram.org/bot{old_bot_token}/sendMessage"
            payload = {
                "chat_id": user.telegram_id,
                "text": text,
                "parse_mode": "Markdown",
                "reply_markup": keyboard,
                "disable_web_page_preview": True
            }
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                success = True
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get('description', f'HTTP {response.status_code}')
        except Exception as e:
            error_msg = str(e)
    
    # Если не получилось со старым ботом, пробуем новый
    if not success and new_bot_token and new_bot_token != old_bot_token:
        try:
            url = f"https://api.telegram.org/bot{new_bot_token}/sendMessage"
            payload = {
                "chat_id": user.telegram_id,
                "text": text,
                "parse_mode": "Markdown",
                "reply_markup": keyboard,
                "disable_web_page_preview": True
            }
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                success = True
                error_msg = None
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get('description', f'HTTP {response.status_code}')
        except Exception as e:
            error_msg = str(e)
    
    return success, error_msg


def send_user_payment_notification_async(user, is_successful=True, tariff_name=None, is_balance_topup=False, payment_order_id=None, payment=None):
    """Отправить уведомление пользователю асинхронно (в фоне)"""
    def send():
        send_user_payment_notification(user, is_successful, tariff_name, is_balance_topup, payment_order_id, payment)
    
    threading.Thread(target=send, daemon=True).start()
