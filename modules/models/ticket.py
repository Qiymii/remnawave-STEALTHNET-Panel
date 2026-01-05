"""
Модели тикетов поддержки
"""
from datetime import datetime, timezone
from modules.core import get_db

db = get_db()

class Ticket(db.Model):
    """Тикет поддержки"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('tickets', lazy=True))
    subject = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='OPEN')  # OPEN, IN_PROGRESS, RESOLVED, CLOSED
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))


class TicketMessage(db.Model):
    """Сообщение в тикете"""
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    ticket = db.relationship('Ticket', backref=db.backref('messages', lazy=True))
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sender = db.relationship('User')
    message = db.Column(db.Text, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))


