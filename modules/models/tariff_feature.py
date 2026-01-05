"""
Модель функций тарифов
"""
from modules.core import get_db

db = get_db()

class TariffFeatureSetting(db.Model):
    """Функции тарифа по уровню"""
    id = db.Column(db.Integer, primary_key=True)
    tier = db.Column(db.String(20), nullable=False)  # basic, pro, elite
    features = db.Column(db.Text, nullable=True)  # JSON массив функций


