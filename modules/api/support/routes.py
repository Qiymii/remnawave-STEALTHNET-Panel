"""
API эндпоинты поддержки

- GET/POST /api/client/support-tickets - Тикеты клиента
- GET /api/admin/support-tickets - Тикеты для администратора
- PATCH /api/admin/support-tickets/<id> - Обновление статуса
- GET /api/support-tickets/<id> - Сообщения тикета
- POST /api/support-tickets/<id>/reply - Ответ на тикет
"""

from flask import jsonify, request
from datetime import datetime, timezone
import os

from modules.core import get_app, get_db
from modules.auth import admin_required, get_user_from_token
from modules.models.ticket import Ticket, TicketMessage
from modules.models.user import User

app = get_app()
db = get_db()


# ============================================================================
# CLIENT TICKETS
# ============================================================================

@app.route('/api/client/support-tickets', methods=['GET', 'POST'])
def client_tickets():
    """Тикеты клиента"""
    user = get_user_from_token()
    if not user:
        return jsonify({"message": "Authentication required"}), 401

    try:
        if request.method == 'GET':
            tickets = Ticket.query.filter_by(user_id=user.id).order_by(Ticket.created_at.desc()).all()
            result = [{
                'id': t.id,
                'subject': t.subject,
                'status': t.status,
                'created_at': t.created_at.isoformat() if t.created_at else None
            } for t in tickets]
            return jsonify(result), 200

        # POST - создание тикета
        data = request.json
        subject = data.get('subject', '').strip()

        if not subject:
            return jsonify({"message": "Subject is required"}), 400

        ticket = Ticket(
            user_id=user.id,
            subject=subject,
            status='OPEN',
            created_at=datetime.now(timezone.utc)
        )
        db.session.add(ticket)
        db.session.flush()

        message_text = data.get('message', '').strip()
        if message_text:
            message = TicketMessage(
                ticket_id=ticket.id,
                sender_id=user.id,
                message=message_text,
                created_at=datetime.now(timezone.utc)
            )
            db.session.add(message)

        db.session.commit()
        
        # Отправляем уведомление админам в группу
        try:
            from modules.notifications import notify_support_ticket
            notify_support_ticket(ticket, user, message_text, is_new_ticket=True)
        except Exception as e:
            print(f"Error sending support ticket notification: {e}")
        
        return jsonify({"message": "Ticket created successfully", "ticket_id": ticket.id}), 201

    except Exception as e:
        db.session.rollback()
        print(f"Error in client_tickets: {e}")
        return jsonify({"message": "Internal Server Error"}), 500


# ============================================================================
# ADMIN TICKETS
# ============================================================================

@app.route('/api/admin/support-tickets', methods=['GET'])
@admin_required
def admin_tickets(current_admin):
    """Тикеты для администратора"""
    try:
        status = request.args.get('status')
        search = request.args.get('search', '').strip().lower()

        query = Ticket.query.join(User).order_by(Ticket.created_at.desc())

        if status:
            query = query.filter(Ticket.status == status)

        if search:
            query = query.filter(
                (Ticket.subject.ilike(f'%{search}%')) |
                (User.email.ilike(f'%{search}%')) |
                (User.telegram_username.ilike(f'%{search}%'))
            )

        tickets = query.all()
        result = [{
            'id': t.id,
            'user_id': t.user_id,
            'user_email': t.user.email if t.user else None,
            'user_telegram_username': t.user.telegram_username if t.user else None,
            'subject': t.subject,
            'status': t.status,
            'created_at': t.created_at.isoformat() if t.created_at else None
        } for t in tickets]

        return jsonify(result), 200

    except Exception as e:
        print(f"Error in admin_tickets: {e}")
        return jsonify({"message": "Internal Server Error"}), 500


@app.route('/api/admin/support-tickets/<int:ticket_id>', methods=['PATCH'])
@app.route('/api/admin/support-tickets/<int:id>', methods=['PATCH'])
@admin_required
def update_ticket_status(current_admin, ticket_id=None, id=None):
    """Обновление статуса тикета"""
    try:
        ticket_id = ticket_id or id
        ticket = db.session.get(Ticket, ticket_id)
        if not ticket:
            return jsonify({"message": "Ticket not found"}), 404

        data = request.json
        new_status = data.get('status')

        if not new_status or new_status not in ['OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED']:
            return jsonify({"message": "Invalid status"}), 400

        ticket.status = new_status
        db.session.commit()

        return jsonify({"message": "Ticket status updated successfully"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"message": "Internal Server Error"}), 500


# ============================================================================
# TICKET MESSAGES
# ============================================================================

@app.route('/api/support-tickets/<int:ticket_id>', methods=['GET'])
@app.route('/api/support-tickets/<int:id>', methods=['GET'])
def get_ticket_msgs(ticket_id=None, id=None):
    """Сообщения тикета"""
    user = get_user_from_token()
    if not user:
        return jsonify({"message": "Authentication required"}), 401

    try:
        ticket_id = ticket_id or id
        ticket = db.session.get(Ticket, ticket_id)
        if not ticket:
            return jsonify({"message": "Ticket not found"}), 404

        if ticket.user_id != user.id and user.role != 'ADMIN':
            return jsonify({"message": "Access denied"}), 403

        messages = TicketMessage.query.filter_by(ticket_id=ticket_id).order_by(TicketMessage.created_at.asc()).all()

        result = {
            'ticket': {
                'id': ticket.id,
                'subject': ticket.subject,
                'status': ticket.status,
                'created_at': ticket.created_at.isoformat() if ticket.created_at else None
            },
            'messages': [{
                'id': m.id,
                'sender_id': m.sender_id,
                'sender_email': m.sender.email if m.sender else None,
                'sender_telegram_username': m.sender.telegram_username if m.sender else None,
                'message': m.message,
                'created_at': m.created_at.isoformat() if m.created_at else None
            } for m in messages]
        }

        return jsonify(result), 200

    except Exception as e:
        print(f"Error in get_ticket_msgs: {e}")
        return jsonify({"message": "Internal Server Error"}), 500


@app.route('/api/support-tickets/<int:ticket_id>/reply', methods=['POST'])
@app.route('/api/support-tickets/<int:id>/reply', methods=['POST'])
def reply_ticket(ticket_id=None, id=None):
    """Ответ на тикет"""
    user = get_user_from_token()
    if not user:
        return jsonify({"message": "Authentication required"}), 401

    try:
        ticket_id = ticket_id or id
        ticket = db.session.get(Ticket, ticket_id)
        if not ticket:
            return jsonify({"message": "Ticket not found"}), 404

        if ticket.user_id != user.id and user.role != 'ADMIN':
            return jsonify({"message": "Access denied"}), 403

        data = request.json
        message_text = data.get('message', '').strip()

        if not message_text:
            return jsonify({"message": "Message is required"}), 400

        message = TicketMessage(
            ticket_id=ticket_id,
            sender_id=user.id,
            message=message_text,
            is_admin=(user.role == 'ADMIN'),
            created_at=datetime.now(timezone.utc)
        )
        db.session.add(message)
        
        # Обновляем статус тикета - всегда OPEN при ответе (как в оригинале)
        ticket.status = 'OPEN'

        db.session.commit()
        
        # Отправляем уведомление админам в группу, если ответил пользователь (не админ)
        if user.role != 'ADMIN':
            try:
                from modules.notifications import notify_support_ticket
                notify_support_ticket(ticket, user, message_text, is_new_ticket=False)
            except Exception as e:
                print(f"Error sending support ticket notification: {e}")

        # Отправляем уведомление в Telegram боты, если ответил админ
        if user.role == 'ADMIN':
            ticket_owner = db.session.get(User, ticket.user_id)
            if ticket_owner and ticket_owner.telegram_id:
                # Импортируем функцию отправки сообщений
                from modules.api.admin.routes import send_telegram_message
                
                # Получаем токены ботов
                old_bot_token = os.getenv("CLIENT_BOT_TOKEN")
                new_bot_token = os.getenv("CLIENT_BOT_V2_TOKEN") or os.getenv("CLIENT_BOT_TOKEN")
                
                # Получаем имя бота для ссылки
                # Приоритет: TELEGRAM_BOT_NAME (старый бот) -> TELEGRAM_BOT_NAME_V2 (новый бот) -> BOT_USERNAME -> CLIENT_BOT_USERNAME
                # Для уведомлений от админа используем старый бот (TELEGRAM_BOT_NAME)
                bot_username = os.getenv("TELEGRAM_BOT_NAME") or os.getenv("TELEGRAM_BOT_NAME_V2") or os.getenv("BOT_USERNAME") or os.getenv("CLIENT_BOT_USERNAME") or "Ahfbabanah_bot"
                if bot_username.startswith('@'):
                    bot_username = bot_username[1:]
                
                # Формируем текст уведомления
                notification_text = (
                    f"<b>📩 Новый ответ в тикете поддержки</b>\n\n"
                    f"<b>Тема:</b> {ticket.subject}\n"
                    f"<b>Ответ:</b> {message_text[:200]}{'...' if len(message_text) > 200 else ''}\n\n"
                    f"💬 <a href='https://t.me/{bot_username}?start=support_{ticket.id}'>Открыть тикет</a>"
                )
                
                # Отправляем в оба бота (если токены доступны)
                import threading
                
                def send_notification(bot_token, telegram_id, text):
                    if bot_token:
                        try:
                            send_telegram_message(bot_token, telegram_id, text)
                        except Exception as e:
                            print(f"Failed to send ticket notification: {e}")
                
                if old_bot_token:
                    threading.Thread(
                        target=send_notification,
                        args=(old_bot_token, ticket_owner.telegram_id, notification_text)
                    ).start()
                
                if new_bot_token and new_bot_token != old_bot_token:
                    threading.Thread(
                        target=send_notification,
                        args=(new_bot_token, ticket_owner.telegram_id, notification_text)
                    ).start()

        # Возвращаем полный объект сообщения, как в оригинале
        return jsonify({
            "id": message.id,
            "message": message.message,
            "sender_email": user.email,
            "sender_id": user.id,
            "sender_role": user.role,
            "created_at": message.created_at.isoformat() if message.created_at else None
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"message": "Internal Server Error"}), 500
