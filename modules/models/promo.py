"""
Модель промокода
"""
from modules.core import get_db

db = get_db()

class PromoCode(db.Model):
    """Промокод"""
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    promo_type = db.Column(db.String(20), nullable=False, default='PERCENT')
    value = db.Column(db.Integer, nullable=False)
    uses_left = db.Column(db.Integer, nullable=False, default=1)
    squad_id = db.Column(db.String(100), nullable=True)  # ID сквада для промокодов типа DAYS

