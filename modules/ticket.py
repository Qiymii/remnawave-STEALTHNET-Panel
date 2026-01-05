"""
Модуль тикетов - реэкспорт из modules.models.ticket

DEPRECATED: Используйте modules.models.ticket напрямую
"""
from modules.models.ticket import Ticket, TicketMessage

__all__ = ['Ticket', 'TicketMessage']
