"""
Модель для системы казино (Колесо Фортуны)
"""
from modules.core import get_db
from datetime import datetime

db = get_db()


class CasinoGame(db.Model):
    """История игр в казино"""
    __tablename__ = 'casino_game'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Ставка и результат
    bet_days = db.Column(db.Integer, nullable=False)  # Ставка в днях
    multiplier = db.Column(db.Float, nullable=False)  # Множитель (0, 0.5, 1, 1.5, 2, 3, 5)
    win_days = db.Column(db.Integer, nullable=False)  # Выигрыш в днях (может быть отрицательным)
    
    # Баланс до и после
    balance_before = db.Column(db.Integer, nullable=False)  # Дней до игры
    balance_after = db.Column(db.Integer, nullable=False)  # Дней после игры
    
    # Метаданные
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связь с пользователем
    user = db.relationship('User', backref=db.backref('casino_games', lazy='dynamic'))
    
    def to_dict(self):
        return {
            'id': self.id,
            'bet_days': self.bet_days,
            'multiplier': self.multiplier,
            'win_days': self.win_days,
            'balance_before': self.balance_before,
            'balance_after': self.balance_after,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class CasinoStats(db.Model):
    """Общая статистика казино"""
    __tablename__ = 'casino_stats'
    
    id = db.Column(db.Integer, primary_key=True)
    total_games = db.Column(db.Integer, default=0)  # Всего игр
    total_bet_days = db.Column(db.Integer, default=0)  # Всего поставлено дней
    total_win_days = db.Column(db.Integer, default=0)  # Всего выиграно дней
    total_lost_days = db.Column(db.Integer, default=0)  # Всего проиграно дней
    house_profit_days = db.Column(db.Integer, default=0)  # Профит казино в днях
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)




